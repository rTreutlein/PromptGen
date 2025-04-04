"""
Module for managing application state
"""
import threading
import os
import json
import time
from typing import Dict, List, Optional

from ..models.signature import SignatureDefinition
from ..models.model import ModelDefinition
from ..config import Config

class AppState:
    """Singleton class for managing application state"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AppState, cls).__new__(cls)
                cls._instance._initialize()
            return cls._instance

    def _initialize(self):
        """Initialize the application state"""
        self.current_model = Config.DEFAULT_MODEL
        self.optimization_running = False
        self.evaluation_results = {"metrics": {}, "results": []}
        
        # Available models as ModelDefinition objects
        self.models = {}
        self._load_default_models()
        
        # Signature management
        self.signatures = {}
        self.current_signature_name = None
        self._load_default_signatures()
        
        # Program management
        self.programs = {}  # Dictionary of program_id -> metadata
        self.current_program_id = None
        self._ensure_directories()
        self.load_available_programs()
        
    def _load_default_models(self):
        """Load default models if none exist"""
        # Check if models directory exists
        if not Config.MODELS_DIR.exists():
            Config.MODELS_DIR.mkdir(exist_ok=True)
        
        # Check if any models exist
        model_files = list(Config.MODELS_DIR.glob("*.json"))
        
        # If no models exist, create default models
        if not model_files:
            default_models = [
                ModelDefinition(
                    name="claude-3-7-sonnet-20250219",
                    provider="anthropic",
                    description="Claude 3.7 Sonnet - Anthropic's powerful model with balanced capabilities",
                    parameters={"temperature": 0.7, "max_tokens": 4000}
                ),
                ModelDefinition(
                    name="claude-3.7-sonnet",
                    provider="openrouter/anthropic",
                    description="Claude 3.7 Sonnet via OpenRouter - Access through OpenRouter API",
                    parameters={"temperature": 0.7, "max_tokens": 4000}
                ),
                ModelDefinition(
                    name="deepseek-reasoner",
                    provider="deepseek",
                    description="DeepSeek Reasoner - Specialized for reasoning tasks",
                    parameters={"temperature": 0.7, "max_tokens": 4000}
                ),
                ModelDefinition(
                    name="deepseek-chat",
                    provider="deepseek",
                    description="DeepSeek Chat - General-purpose chat model",
                    parameters={"temperature": 0.7, "max_tokens": 4000}
                ),
                ModelDefinition(
                    name="gpt-4o",
                    provider="openai",
                    description="GPT-4o - OpenAI's latest multimodal model",
                    parameters={"temperature": 0.7, "max_tokens": 4000}
                ),
                ModelDefinition(
                    name="gpt-4o-mini",
                    provider="openai",
                    description="GPT-4o Mini - Smaller, faster version of GPT-4o",
                    parameters={"temperature": 0.7, "max_tokens": 4000}
                ),
                ModelDefinition(
                    name="o3-mini",
                    provider="openai",
                    description="o3-mini - OpenAI's o3 mini model",
                    parameters={"temperature": 1.0, "max_tokens": 5000}
                ),
                ModelDefinition(
                    name="gemini-2.0-pro-exp-02-05:free",
                    provider="openrouter/google",
                    description="Google Gemini 2.0 Pro via OpenRouter",
                    parameters={"temperature": 0.7, "max_tokens": 4000}
                )
            ]
            
            # Save and add each default model
            for model in default_models:
                self._save_model(model)
                self.models[model.full_name] = model
        else:
            # Load existing models
            for filepath in model_files:
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                        model = ModelDefinition.from_dict(data)
                        self.models[model.full_name] = model
                except Exception as e:
                    print(f"Error loading model from {filepath}: {e}")
                    
    @property
    def AVAILABLE_MODELS(self) -> List[str]:
        """Get list of available model names"""
        return list(self.models.keys())
    
    def _ensure_directories(self):
        """Create necessary directories if they don't exist"""
        Config.PROGRAM_DIR.mkdir(exist_ok=True)
        Config.SAMPLES_DIR.mkdir(exist_ok=True)
        Config.SIGNATURES_DIR.mkdir(exist_ok=True)
        Config.MODELS_DIR.mkdir(exist_ok=True)
    
    def _load_default_signatures(self):
        """Load default signatures if none exist"""
        # Check if signatures directory exists
        if not Config.SIGNATURES_DIR.exists():
            Config.SIGNATURES_DIR.mkdir(exist_ok=True)
        
        # Check if any signatures exist
        signature_files = list(Config.SIGNATURES_DIR.glob("*.json"))
        
        # If no signatures exist, create default PLN signature
        if not signature_files:
            pln_signature = SignatureDefinition(
                name="PLNTask",
                signature_class_def="""class PLNTask(dspy.Signature):
    \"\"\"
    Convert the given english to PLN.
    If it is a question construct one ore more queries to answer it.
    If it is a statement construct one or more statements to add the knowledge to the KB.
    Provide type definitions for all predicates.

    Given Types are:
    (: Implication (-> (: $implicant Type) (: $consequent Type) Type))
    (: And (-> (: $a Type) (: $b Type) Type))
    (: Or (-> (: $a Type) (: $b Type) Type))
    (: Equivalence (-> (: $a Type) (: $b Type) Type))
    (: WithTV (-> (: $a Type) (: $tv TV) Type))
    (: STV (-> (: $strength Number) (: $confidence Number) TV))

    All queries or statments should be wrapped in WithTV.
    Example Statment:
    (: proofname (WithTV (Predicate object) (STV 1.0 1.0)))
    Example Query :
    (: $query (WithTV (Predicate object) $tv))
    meaning (try to find a proof $query that Predicate applies to object and get me the $tv)
    Predicate or object could also be varaibles in a query.
    \"\"\"
    english = dspy.InputField(desc="English text to convert to PLN")
    pln_types = dspy.OutputField(desc="PLN type definitions")
    pln_statements = dspy.OutputField(desc="PLN statements")
    pln_query = dspy.OutputField(desc="PLN query")""",
                description="Convert English to PLN (Probabilistic Logic Network) syntax",
                input_fields=["english"],
                output_fields=["pln_types", "pln_statements", "pln_query"]
            )
            
            # Save the default signature
            self._save_signature(pln_signature)
            self.signatures[pln_signature.name] = pln_signature
            self.current_signature_name = pln_signature.name
        else:
            # Load existing signatures
            for filepath in signature_files:
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                        signature = SignatureDefinition.from_dict(data)
                        self.signatures[signature.name] = signature
                except Exception as e:
                    print(f"Error loading signature from {filepath}: {e}")
            
            # Set current signature to the first one if none is selected
            if not self.current_signature_name and self.signatures:
                self.current_signature_name = list(self.signatures.keys())[0]
    
    def _save_signature(self, signature: SignatureDefinition) -> bool:
        """Save signature definition to file"""
        try:
            filepath = Config.SIGNATURES_DIR / f"{signature.name}.json"
            with open(filepath, "w") as f:
                json.dump(signature.to_dict(), f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving signature {signature.name}: {e}")
            return False
    
    def _save_model(self, model: ModelDefinition) -> bool:
        """Save model definition to file"""
        try:
            # Use a sanitized filename based on the full_name
            sanitized_name = model.full_name.replace('/', '_')
            filepath = Config.MODELS_DIR / f"{sanitized_name}.json"
            with open(filepath, "w") as f:
                json.dump(model.to_dict(), f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving model {model.full_name}: {e}")
            return False
    
    def add_model(self, model: ModelDefinition) -> bool:
        """Add a new model definition"""
        if model.full_name in self.models:
            return False
        
        self.models[model.full_name] = model
        self._save_model(model)
        return True
    
    def update_model(self, model: ModelDefinition) -> bool:
        """Update an existing model"""
        if model.full_name not in self.models:
            return False
            
        self.models[model.full_name] = model
        self._save_model(model)
        return True
        
    def delete_model(self, model_name: str) -> bool:
        """Delete a model"""
        if model_name not in self.models:
            return False
            
        try:
            # Delete the model file
            sanitized_name = model_name.replace('/', '_')
            filepath = Config.MODELS_DIR / f"{sanitized_name}.json"
            if filepath.exists():
                filepath.unlink()
                
            # Remove from models dictionary
            del self.models[model_name]
            
            # Reset current model if needed
            if self.current_model == model_name:
                if self.models:
                    self.current_model = list(self.models.keys())[0]
                else:
                    self.current_model = None
                    
            return True
        except Exception as e:
            print(f"Error deleting model {model_name}: {e}")
            return False
    
    def get_model(self, name: str) -> Optional[ModelDefinition]:
        """Get a model definition by name"""
        return self.models.get(name)
    
    def set_current_model(self, name: str) -> bool:
        """Set the current model"""
        if name in self.models:
            self.current_model = name
            return True
        return False
    
    def get_current_model(self) -> Optional[ModelDefinition]:
        """Get the current model definition"""
        if self.current_model:
            return self.models.get(self.current_model)
        return None
    
    def add_signature(self, signature: SignatureDefinition) -> bool:
        """Add a new signature definition"""
        if signature.name in self.signatures:
            return False
        
        self.signatures[signature.name] = signature
        self._save_signature(signature)
        return True
    
    def get_signature(self, name: str) -> Optional[SignatureDefinition]:
        """Get a signature definition by name"""
        return self.signatures.get(name)
    
    def set_current_signature(self, name: str) -> bool:
        """Set the current signature"""
        if name in self.signatures:
            self.current_signature_name = name
            return True
        return False
    
    def get_current_signature(self) -> Optional[SignatureDefinition]:
        """Get the current signature definition"""
        if self.current_signature_name:
            return self.signatures.get(self.current_signature_name)
        return None
    
    def load_available_programs(self):
        """Load metadata for all available programs"""
        programs_dir = Config.PROGRAM_DIR
        self.programs = {}
        
        # Find all program directories
        if programs_dir.exists():
            for program_id in os.listdir(programs_dir):
                program_path = programs_dir / program_id
                if program_path.is_dir():
                    metadata_path = program_path / "metadata.json"
                    if metadata_path.exists():
                        try:
                            with open(metadata_path, "r") as f:
                                metadata = json.load(f)
                            # Add creation time from file if not in metadata
                            if "created_at" not in metadata:
                                metadata["created_at"] = os.path.getctime(metadata_path)
                            # Add program ID to metadata
                            metadata["id"] = program_id
                            # Add to programs dictionary
                            self.programs[program_id] = metadata
                        except Exception as e:
                            print(f"Error loading program {program_id}: {e}")
        
        # Set current program to the most recent if none is selected
        if not self.current_program_id and self.programs:
            # Sort by creation time (newest first)
            sorted_programs = sorted(self.programs.items(), 
                                    key=lambda x: x[1].get("created_at", 0), 
                                    reverse=True)
            self.current_program_id = sorted_programs[0][0]
    
    def set_current_program(self, program_id):
        """Set the current program"""
        if program_id in self.programs:
            self.current_program_id = program_id
            return True
        return False
    
    def get_programs_for_signature(self, signature_name: str) -> Dict:
        """Get all programs for a specific signature
        
        This will only return programs that are compatible with the given signature.
        Programs are only compatible if they were created with exactly the same signature.
        """
        return {
            program_id: metadata for program_id, metadata in self.programs.items()
            if metadata.get("signature_name") == signature_name
        }
        
    def create_new_program(self, model_name: str, base_program_id: str = None, signature_name: str = None):
        """Create a new empty program
        
        Args:
            model_name (str): The model to use for the program
            base_program_id (str, optional): ID of program to use as base
            signature_name (str, optional): Name of signature to use
            
        Returns:
            str: The ID of the created program
        """
        import dspy
        import importlib.util
        from ..utils.program_utils import save_program
        
        # Use provided signature name or current signature
        sig_name = signature_name or self.current_signature_name
        if not sig_name or sig_name not in self.signatures:
            raise ValueError("No signature selected")
        
        signature_def = self.signatures[sig_name]
        
        # Create a module to execute the signature class definition
        module_name = f"dynamic_signature_{int(time.time())}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        module.dspy = dspy
        
        # Execute the signature class definition in the module's context
        exec(signature_def.signature_class_def, module.__dict__)
        
        # Get the class from the module
        signature_class = getattr(module, sig_name)
        
        # Create a new task using the signature
        task = dspy.ChainOfThought(signature_class)
        
        # Save the program using the utility function
        program_id = save_program(
            task,
            model_name,
            sig_name,
            signature_def.description,
            base_program_id
        )
        
        # Update current program in app state
        self.current_program_id = program_id
        self.load_available_programs()  # Refresh program list
        
        return program_id
    
    def delete_program(self, program_id):
        """Delete a program
        
        Args:
            program_id (str): The ID of the program to delete
            
        Returns:
            bool: True if the program was deleted, False otherwise
        """
        import shutil
        
        if program_id not in self.programs:
            return False
        
        program_dir = Config.PROGRAM_DIR / program_id
        if not program_dir.exists():
            return False
        
        try:
            # Delete the program directory
            shutil.rmtree(program_dir)
            
            # Update the current program if needed
            if self.current_program_id == program_id:
                # Find another program to set as current
                self.current_program_id = None
                self.load_available_programs()
            else:
                # Just remove from the programs dictionary
                del self.programs[program_id]
                
            return True
        except Exception as e:
            print(f"Error deleting program {program_id}: {e}")
            return False
