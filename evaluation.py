import dspy
from typing import List, Dict, Any, Optional
import os
from .samples import SampleManager
from .state import AppState
from .optimization import Optimizer
from .metrics import judge_metric

class Evaluator:
    """Handles evaluation of the optimized model against sample data"""
    
    def __init__(self, app_state: AppState, sample_manager: SampleManager):
        self.app_state = app_state
        self.sample_manager = sample_manager
    
    def load_optimized_task(self):
        """Load the optimized task from disk"""
        try:
            # Use the current program ID from app state
            program_id = self.app_state.current_program_id
            if not program_id:
                print("No program selected")
                return None
                
            program_dir = f"./programs/{program_id}/"
            if not os.path.exists(program_dir):
                print(f"Program directory not found: {program_dir}")
                return None
                
            optimized_task = dspy.load(program_dir)
            print(f"Successfully loaded optimized task from {program_dir}: {type(optimized_task)}")
            return optimized_task
        except Exception as e:
            print(f"Failed to load optimized task: {e}")
            return None
    
    def evaluate_similarity(self, example_data: Dict[str, Any], prediction: Any, lm: dspy.LM) -> Dict[str, Any]:
        """Use the same metric as optimization to evaluate similarity between expected and predicted outputs"""
        
        try:
            # Create example with the data
            example = dspy.Example(**example_data)
            score , reasoning = judge_metric(example, prediction)
            
            return {
                "score": int(score * 100),
                "explanation": reasoning
            }
        except Exception as e:
            print(f"Error in similarity evaluation: {e}")
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
            eval_lm = dspy.LM(model_name)
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
                similarity_lm = dspy.LM(similarity_model_name)
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
                    # Check if sample has required fields
                    if not all(field in sample for field in ["english", "pln_types", "pln_statements", "pln_questions"]):
                        print(f"Skipping sample {i+1}: missing required fields")
                        continue
                    
                    input_value = sample.get("english", "")
                    print(f"Evaluating sample {i+1}/{len(samples)}: {input_value[:50]}...")
                    
                    # Run the model on the input with the specific LM instance
                    with dspy.context(lm=eval_lm):
                        prediction = optimized_task(english=input_value)
                    
                    # Create example data dictionary
                    example_data = {
                        "english": sample.get("english", ""),
                        "pln_types": sample.get("pln_types", ""),
                        "pln_statements": sample.get("pln_statements", ""),
                        "pln_questions": sample.get("pln_questions", "")
                    }
                    
                    # Calculate similarity using the optimization metric
                    similarity_result = self.evaluate_similarity(
                        example_data=example_data,
                        prediction=prediction,
                        lm=similarity_lm
                    )
                    
                    # Use the holistic score
                    overall_score = similarity_result["score"]
                    
                    # Create result dictionary
                    result = {
                        "sample_id": i,
                        "similarity_result": similarity_result,
                        "overall_score": overall_score,
                        "input_english": sample.get("english", ""),
                        "expected_pln_types": sample.get("pln_types", ""),
                        "expected_pln_statements": sample.get("pln_statements", ""),
                        "expected_pln_questions": sample.get("pln_questions", ""),
                        "predicted_pln_types": getattr(prediction, "pln_types", "N/A"),
                        "predicted_pln_statements": getattr(prediction, "pln_statements", "N/A"),
                        "predicted_pln_questions": getattr(prediction, "pln_questions", "N/A")
                    }
                    
                    results.append(result)
                except Exception as e:
                    print(f"Error evaluating sample {i+1}: {e}")
                    
                    # Create error result
                    error_result = {
                        "sample_id": i,
                        "similarity_result": {"score": 0, "explanation": "Error"},
                        "overall_score": 0,
                        "error": str(e),
                        "input_english": sample.get("english", ""),
                        "expected_pln_types": sample.get("pln_types", ""),
                        "expected_pln_statements": sample.get("pln_statements", ""),
                        "expected_pln_questions": sample.get("pln_questions", ""),
                        "predicted_pln_types": "ERROR",
                        "predicted_pln_statements": "ERROR",
                        "predicted_pln_questions": "ERROR"
                    }
                    
                    results.append(error_result)
                    
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
                "status": "success",
                "metrics": metrics,
                "results": results
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Evaluation failed: {str(e)}",
                "metrics": {},
                "full_output": f"Error: {str(e)}"
            }
