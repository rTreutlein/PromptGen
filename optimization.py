from typing import List, Dict
import dspy
import json
import os
import time
from .samples import SampleManager
from .state import AppState
from .metrics import judge_metric

class Optimizer:
    """Handles optimization process for the language model"""
    
    def __init__(self, app_state: AppState, sample_manager: SampleManager):
        self.app_state = app_state
        self.sample_manager = sample_manager
        self.running = False

    def _prepare_training_data(self, samples: List[Dict]) -> List[dspy.Example]:
        """Prepare DSPy examples from loaded samples"""
        examples = []
        for d in samples:
            if "english" in d and "pln_types" in d and "pln_statements" in d and "pln_questions" in d:
                example = dspy.Example(
                    english=d["english"],
                    pln_types=d["pln_types"],
                    pln_statements=d["pln_statements"],
                    pln_questions=d["pln_questions"]
                ).with_inputs("english")
                examples.append(example)
        
        return examples

    def run_optimization(self, model_name: str) -> None:
        """Run the optimization process with thread safety"""
        if self.running:
            return

        self.running = True
        try:
            thread_lm = dspy.LM(model_name)
            if not thread_lm:
                return
            
            samples = self.sample_manager.load_samples()
            training_data = self._prepare_training_data(samples)
            
            if not training_data:
                raise ValueError("No valid training data found")

            # Define the PLN signature
            class PLNTask(dspy.Signature):
                """Convert English text to Programming Language for Thought (PLN)"""
                english = dspy.InputField(desc="English text to convert to PLN")
                pln_types = dspy.OutputField(desc="PLN type definitions")
                pln_statements = dspy.OutputField(desc="PLN statements")
                pln_questions = dspy.OutputField(desc="PLN questions")

            # Base task can either be a new one or loaded from the current program
            if self.app_state.current_program_id and os.path.exists(f"./programs/{self.app_state.current_program_id}/program.pkl"):
                # Load the current program as a base
                print(f"Loading base program from {self.app_state.current_program_id}")
                try:
                    base_task = dspy.load(f"./programs/{self.app_state.current_program_id}/")
                    print(f"Successfully loaded base task: {type(base_task)}")
                    
                    # If optimization is complete, use the same optimization technique
                    optimized_task = dspy.MIPROv2(
                        metric=self._optimization_metric,
                        auto="light"
                    ).compile(base_task, trainset=training_data, requires_permission_to_run=False)
                except Exception as e:
                    print(f"Failed to load base task, creating new one: {e}")
                    # Fall back to creating a new task
                    task = dspy.ChainOfThought(PLNTask)
                    optimized_task = dspy.MIPROv2(
                        metric=self._optimization_metric,
                        auto="light"
                    ).compile(task, trainset=training_data, requires_permission_to_run=False)
            else:
                # Create a new task using the PLN signature
                print("Creating new base task")
                task = dspy.ChainOfThought(PLNTask)
                optimized_task = dspy.MIPROv2(
                    metric=self._optimization_metric,
                    auto="light"
                ).compile(task, trainset=training_data, requires_permission_to_run=False)
            
            # Generate a unique ID for the program
            program_id = f"program_{int(time.time())}"
            program_dir = f"./programs/{program_id}/"
            
            # Create directory if it doesn't exist
            os.makedirs(program_dir, exist_ok=True)
            
            # Save program to the directory
            print(f"Saving optimized program to {program_dir}")
            optimized_task.save(program_dir, save_program=True)
            
            # Add additional metadata
            metadata_path = os.path.join(program_dir, "metadata.json")
            if os.path.exists(metadata_path):
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)
                
                # Add additional metadata
                metadata["model"] = model_name
                metadata["created_at"] = time.time()
                metadata["task_name"] = "English to PLN Converter"
                metadata["base_program_id"] = self.app_state.current_program_id
                
                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, indent=2)
            
            # Update current program in app state
            self.app_state.current_program_id = program_id
            self.app_state.load_available_programs()  # Refresh program list
        except Exception as e:
            print(f"Optimization error: {e}")
        finally:
            self.running = False

    def _optimization_metric(self, example, pred, trace=None) -> float:
        """Metric for optimization process"""
        return judge_metric(example, pred).similarity
