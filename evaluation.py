import dspy
from typing import List, Dict, Any, Optional
from .models import ModelManager
from .samples import SampleManager
from .state import AppState

class Evaluator:
    """Handles evaluation of the optimized model against sample data"""
    
    def __init__(self, app_state: AppState, model_manager: ModelManager, sample_manager: SampleManager):
        self.app_state = app_state
        self.model_manager = model_manager
        self.sample_manager = sample_manager
    
    def load_optimized_task(self):
        """Load the optimized task from disk"""
        try:
            optimized_task = dspy.load("./program/")
            print(f"Successfully loaded optimized task: {type(optimized_task)}")
            return optimized_task
        except Exception as e:
            print(f"Failed to load optimized task: {e}")
            return None
    
    def evaluate_similarity_with_llm(self, expected_types: str, expected_statements: str, 
                                    expected_questions: str, predicted_types: str, 
                                    predicted_statements: str, predicted_questions: str, 
                                    lm: dspy.LM) -> Dict[str, Any]:
        """Use LLM to evaluate similarity between expected and predicted outputs holistically"""
        
        class HolisticSimilarityEvaluator(dspy.Signature):
            """Evaluate the similarity between expected and predicted outputs holistically."""
            expected_types = dspy.InputField(desc="The expected types")
            expected_statements = dspy.InputField(desc="The expected statements")
            expected_questions = dspy.InputField(desc="The expected questions")
            predicted_types = dspy.InputField(desc="The predicted types")
            predicted_statements = dspy.InputField(desc="The predicted statements")
            predicted_questions = dspy.InputField(desc="The predicted questions")
            similarity_score = dspy.OutputField(desc="Overall similarity score from 0-100")
            explanation = dspy.OutputField(desc="Detailed explanation of the similarity assessment")
        
        evaluator = dspy.Predict(HolisticSimilarityEvaluator)
        
        try:
            with dspy.context(lm=lm):
                result = evaluator(
                    expected_types=expected_types,
                    expected_statements=expected_statements,
                    expected_questions=expected_questions,
                    predicted_types=predicted_types,
                    predicted_statements=predicted_statements,
                    predicted_questions=predicted_questions
                )
                
            # Try to convert score to int, default to 0 if not possible
            try:
                score = int(result.similarity_score)
                # Ensure score is within 0-100 range
                score = max(0, min(100, score))
            except (ValueError, TypeError):
                score = 0
                
            return {
                "score": score,
                "explanation": result.explanation
            }
        except Exception as e:
            print(f"Error in LLM holistic similarity evaluation: {e}")
            return {
                "score": 0,
                "explanation": f"Error: {str(e)}"
            }
    
    def run_evaluation(self, model_name: str, similarity_model_name: Optional[str] = None) -> Dict[str, Any]:
        """Run the evaluation on the optimized model
        
        Args:
            model_name: Model to use for running the optimized task
            similarity_model_name: Model to use for similarity scoring (defaults to model_name if None)
        """
        try:
            # Get model instances
            eval_lm = self.model_manager.get_lm_instance(model_name)
            if eval_lm is None:
                return {
                    "error": f"Failed to initialize evaluation model {model_name}",
                    "metrics": {},
                    "full_output": f"Error initializing evaluation model {model_name}"
                }
            
            # Use the same model for similarity if not specified
            if similarity_model_name is None or similarity_model_name == "":
                similarity_lm = eval_lm
            else:
                similarity_lm = self.model_manager.get_lm_instance(similarity_model_name)
                if similarity_lm is None:
                    return {
                        "error": f"Failed to initialize similarity model {similarity_model_name}",
                        "metrics": {},
                        "full_output": f"Error initializing similarity model {similarity_model_name}"
                    }
                
            # Load optimized task
            optimized_task = self.load_optimized_task()
            if optimized_task is None:
                return {
                    "error": "Failed to load optimized task",
                    "metrics": {},
                    "full_output": "Error loading optimized task"
                }
            
            # Load samples
            samples = self.sample_manager.load_samples()
            if not samples:
                return {
                    "error": "No samples to evaluate",
                    "metrics": {},
                    "full_output": "Error: No samples found"
                }
                
            # Evaluate model on samples
            results = []
            for i, sample in enumerate(samples):
                try:
                    print(f"Evaluating sample {i+1}/{len(samples)}: {sample['input'][:50]}...")
                    english = sample["input"]
                    expected_types = sample["types"]
                    expected_statements = sample["statements"]
                    expected_questions = sample.get("questions", "")
                    
                    # Run the model on the input with the specific LM instance
                    with dspy.context(lm=eval_lm):
                        prediction = optimized_task(english=english)
                    
                    # Calculate holistic similarity score
                    similarity_result = self.evaluate_similarity_with_llm(
                        expected_types=expected_types,
                        expected_statements=expected_statements,
                        expected_questions=expected_questions,
                        predicted_types=prediction.pln_types,
                        predicted_statements=prediction.pln_statements,
                        predicted_questions=prediction.pln_questions,
                        lm=similarity_lm
                    )
                    
                    # Use the holistic score
                    overall_score = similarity_result["score"]
                    
                    # Store the results
                    results.append({
                        "sample_id": i,
                        "input": english,
                        "expected_types": expected_types,
                        "predicted_types": prediction.pln_types,
                        "expected_statements": expected_statements,
                        "predicted_statements": prediction.pln_statements,
                        "expected_questions": expected_questions,
                        "predicted_questions": prediction.pln_questions,
                        "similarity_result": similarity_result,
                        "overall_score": overall_score
                    })
                except Exception as e:
                    print(f"Error evaluating sample {i+1}: {e}")
                    results.append({
                        "sample_id": i,
                        "input": sample["input"],
                        "expected_types": sample["types"],
                        "predicted_types": "ERROR",
                        "expected_statements": sample["statements"],
                        "predicted_statements": "ERROR",
                        "expected_questions": sample.get("questions", ""),
                        "predicted_questions": "ERROR",
                        "similarity_result": {"score": 0, "explanation": "Error"},
                        "overall_score": 0,
                        "error": str(e)
                    })
                    
            # Calculate overall metrics
            total = len(results)
            errors = sum(1 for r in results if "error" in r)
            
            # Calculate average similarity score
            avg_overall_score = sum(r.get("overall_score", 0) for r in results) / total if total > 0 else 0
            
            # Sort results by score (lowest first to identify hardest samples)
            results.sort(key=lambda r: r.get("overall_score", 0))
            
            # Generate metrics
            metrics = {
                "Total Samples": total,
                "Errors": f"{errors}/{total} ({errors/total:.2%})",
                "Avg Similarity Score": f"{avg_overall_score:.1f}/100"
            }
            
            # Return the evaluation results
            return {
                "metrics": metrics,
                "results": results
            }
        except Exception as e:
            return {
                "error": f"Evaluation failed: {str(e)}",
                "metrics": {},
                "full_output": f"Error: {str(e)}"
            }
