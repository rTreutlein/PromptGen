from typing import List, Dict
import dspy
import json
import os
from samples import SampleManager

class Optimizer:
    """Handles optimization process for the language model"""
    
    def __init__(self, sample_manager: SampleManager):
        self.sample_manager = sample_manager
        self.running = False

    def _prepare_training_data(self, samples: List[Dict]) -> List[dspy.Example]:
        """Prepare DSPy examples from loaded samples"""
        return [
            dspy.Example(
                english=d["input"], 
                pln_types=d["types"],
                pln_statements=d["statements"],
                pln_questions=d.get("questions", "")
            ).with_inputs('english') 
            for d in samples
        ]

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

            task = dspy.ChainOfThought(
                'english -> pln_types: str, pln_statements: str, pln_questions: str'
            )
            
            optimized_task = dspy.MIPROv2(
                metric=self._optimization_metric,
                auto="light"
            ).compile(task, trainset=training_data, requires_permission_to_run=False)
            
            optimized_task.save("./program/", save_program=True)
        except Exception as e:
            print(f"Optimization error: {e}")
        finally:
            self.running = False

    def _optimization_metric(self, example, pred, trace=None) -> float:
        """Metric for optimization process"""
        judge = dspy.ChainOfThought(
            'true_types, true_statements, true_questions, pred_types, pred_statements, pred_questions -> similarity: float'
        )
        return judge(
            true_types=example.pln_types, 
            true_statements=example.pln_statements,
            true_questions=example.pln_questions,
            pred_types=pred.pln_types,
            pred_statements=pred.pln_statements,
            pred_questions=pred.pln_questions
        ).similarity
