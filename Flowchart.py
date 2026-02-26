from Step import Step, dictionary_to_step
import json


class Flowchart:
    """In-memory graph of steps; utility helpers to manage nodes/edges."""
    
    def __init__(self, name, framework):
        """This method initializes the flowchart with the given name"""
        self.name = name #String
        self.steps = {} #Dictionary {step.id : step}
        self.start_id = None #String
        self.framework = framework #String
    
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
        return self.steps.get(self.start_id, None)
    
    def remove_step(self, step_id):
        """Remove a step from the flowchart."""
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
        return (f"Flowchart(name='{self.name}', steps={self.steps}, start_id='{self.start_id}')")

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
            'framework': self.framework
        }

    def dictionary_to_flowchart(self, dictionary):
        """Create flowchart from dictionary."""
        flowchart = Flowchart(dictionary['name'])
        flowchart.start_id = dictionary['start_id']
        
        # Loop through each step in the dictionary
        for step_id, step_data in dictionary['steps'].items():
            # Convert dictionary to Step object and add to flowchart
            step = dictionary_to_step(step_data)
            flowchart.add_step(step)
        
        return flowchart
    
    def save_to_file(self, filename):
        """Save flowchart to JSON file."""
        
        # Convert flowchart to dictionary
        flowchart_dict = self.flowchart_to_dictionary()
        
        # Open file and write JSON
        with open(filename, 'w') as file:
            json.dump(flowchart_dict, file, indent=2)
        
        print(f"Flowchart saved to {filename}")
    
    def load_from_file(self, filename):
        """Load flowchart from JSON file."""
        
        # Open file and read JSON
        with open(filename, 'r') as file:
            flowchart_dict = json.load(file)
        
        # Convert dictionary back to Flowchart object
        flowchart = self.dictionary_to_flowchart(flowchart_dict)
        
        print(f"Flowchart loaded from {filename}")
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
        
        # Set framework if provided
        if 'framework' in ai_data:
            self.framework = ai_data['framework']
        
        # Loop through each step in AI response
        for step_data in ai_data['steps']:
            
            # Extract data
            step_id = step_data['id']
            step_type = step_data.get('type', 'process')
            description = step_data['description']
            filenames = step_data.get('filenames', [])
            next_steps = step_data['next']
            
            # Create a Step object
            step = Step(
                id=step_id,
                description=description,
                filenames=filenames,
                children=next_steps
            )
            
            # Add step to flowchart
            self.add_step(step)
            
            # Set the first step as start if it's type "start"
            if step_type == "start" and self.start_id is None:
                self.set_start(step_id)
        
        return self


