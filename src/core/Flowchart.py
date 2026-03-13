import os
import uuid
from src.core.Step import Step, dictionary_to_step
import json


class Flowchart:
    """In-memory graph of steps; utility helpers to manage nodes/edges."""
    
    def __init__(self, name, framework="", project_root=None, flowchart_id=None):
        """This method initializes the flowchart with the given name"""
        self.name = name  # String
        self.framework = framework  # String
        self.project_root = project_root  # Path to project directory
        self.flowchart_id = flowchart_id or uuid.uuid4().hex  # Unique ID
        self.steps = {}  # Dictionary {step.id : step}
        self.start_id = None  # String
    
    def add_step(self, step):
        """Add a step to the flowchart."""
        self.steps[step.id] = step
    
    def get_step(self, step_id):
        """Get a step by its ID."""
        return self.steps.get(step_id, None)
    
    def set_start(self, step_id):
        """Set the starting step ID."""
        self.start_id = step_id
    
    def get_start(self):
        """Get the starting step object."""
        if self.start_id and self.start_id in self.steps:
            return self.steps.get(self.start_id, None)
        if not self.steps:
            return None
        # Infer root when start_id is missing.
        all_ids = set(self.steps.keys())
        child_ids = set()
        for step in self.steps.values():
            for child_id in step.children or []:
                child_ids.add(child_id)
        roots = [sid for sid in all_ids if sid not in child_ids]
        if roots:
            return self.steps.get(roots[0])
        return next(iter(self.steps.values()), None)
    
    def remove_step(self, step_id):
        """Remove a step from the flowchart."""
        if step_id in self.steps:
            del self.steps[step_id]
    
    def get_all_steps(self):
        """Get all step IDs."""
        return list(self.steps.keys()) 
    
    def get_children_steps(self, step_id): 
        """Get children IDs of a step."""
        step = self.steps.get(step_id) 
        if step is None:
            return []
        return step.children
    
    def __repr__(self):
        """String representation of the flowchart."""
        return (f"Flowchart(name='{self.name}', steps={self.steps}, "
                f"start_id='{self.start_id}', framework='{self.framework}')")
    
    def flowchart_to_dictionary(self):
        """Convert flowchart to dictionary for saving."""
        # Create empty dictionary for steps
        steps_dict = {}
        
        # Loop through each step in the flowchart
        for step_id, step in self.steps.items():
            # Convert each Step object to a dictionary
            step_dict = step.step_to_dictionary()
            # Add it to our steps dictionary
            steps_dict[step_id] = step_dict
        
        # Return the complete flowchart data
        return {
            'name': self.name,
            'start_id': self.start_id,
            'steps': steps_dict,
            'framework': self.framework,
            'project_root': self.project_root,
            'flowchart_id': self.flowchart_id
        }
    
    def dictionary_to_flowchart(self, dictionary, project_path=None):
        """Create flowchart from dictionary."""
        project_root = dictionary.get('project_root') or project_path or ""
        flowchart = Flowchart(
            name=dictionary['name'],
            framework=dictionary.get('framework', ""),
            project_root=project_root,
            flowchart_id=dictionary.get('flowchart_id')
        )
        
        # Loop through each step in the dictionary
        for step_id, step_data in dictionary['steps'].items():
            # Convert dictionary to Step object and add to flowchart
            step = dictionary_to_step(step_data)
            flowchart.add_step(step)

        if not flowchart.start_id:
            start = flowchart.get_start()
            if start:
                flowchart.start_id = start.id
        
        return flowchart
    
    def save_to_file(self, project_id, flowchart_dict):
        """Save flowchart to JSON file."""
        appdata_root = os.path.join(os.getenv("APPDATA", ""), "SVCA")
        os.makedirs(appdata_root, exist_ok=True)
        project_path = os.path.join(appdata_root, f"{project_id}.flowchart.json")
        
        # Open file and write JSON
        with open(project_path, 'w', encoding='utf-8') as file:
            json.dump(flowchart_dict, file, indent=2)
    
    def load_from_file(self, project_id):
        """Load flowchart from JSON file."""
        appdata_root = os.path.join(os.getenv("APPDATA", ""), "SVCA")
        os.makedirs(appdata_root, exist_ok=True)
        project_path = os.path.join(appdata_root, f"{project_id}.flowchart.json")
        
        # Open file and read JSON
        with open(project_path, 'r', encoding='utf-8') as file:
            flowchart_dict = json.load(file)
        
        # Convert dictionary back to Flowchart object
        flowchart = self.dictionary_to_flowchart(flowchart_dict)
        
        return flowchart

    def update_step_description(self, step_id, new_description):
        """Update the description of a step."""
        step = self.get_step(step_id)
        if step:
            step.description = new_description
            return True
        return False
    
    def add_child_to_step(self, step_id, child_id):
        """Add a child connection to a step."""
        step = self.get_step(step_id)
        if step:
            if child_id not in step.children:
                step.children.append(child_id)
            return True
        return False
    
    def remove_child_from_step(self, step_id, child_id):
        """Remove a child connection from a step."""
        step = self.get_step(step_id)
        if step:
            if child_id in step.children:
                step.children.remove(child_id)
            return True
        return False
        
    def create_from_ai_response(self, ai_data):
        """
        Take AI response data and create flowchart.
        """
        def _normalize_children(children):
            if not children:
                return []
            normalized = []
            for child in children:
                if isinstance(child, dict):
                    child_id = child.get("id") or child.get("name")
                    if child_id:
                        normalized.append(str(child_id))
                else:
                    normalized.append(str(child))
            return normalized

        # Set framework if provided
        if 'framework' in ai_data:
            self.framework = ai_data['framework']
        
        # Loop through each step in AI response
        for step_data in ai_data['nodes']:
            # Extract data
            step_id = step_data['id']
            step_type = step_data.get('type', 'process')
            description = step_data['description']
            filenames = step_data.get('filenames', [])
            files_to_import = step_data.get('files_to_import', [])
            command = step_data.get('command', [])
            next_steps = _normalize_children(step_data.get('children', []))
            
            # Prepend project root to filenames if project_root is set
            if self.project_root:
                filepath = os.path.join(self.project_root, "")
                filenames = [os.path.join(filepath, f) if not os.path.isabs(f) else f 
                            for f in filenames]
                files_to_import = [os.path.join(filepath, f) if not os.path.isabs(f) else f 
                                  for f in files_to_import]
            
            # Create a Step object
            step = Step(
                id=step_id,
                description=description,
                filenames=filenames,
                files_to_import=files_to_import,
                command=command,
                children=next_steps
            )
            
            # Add step to flowchart
            self.add_step(step)
            
            self.set_start(step_id)
        
        return self
