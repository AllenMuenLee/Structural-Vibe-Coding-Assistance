class Step:
    
    def __init__(self, id, description, filenames, children):
        """
        Initialize a Step object (Node)s.
        
        Arguments:
            id: Unique identifier for this step (String)
            description: What this step does (Stirng)
            children: List of IDs of steps that come after this one (List of Step objects' id)
        """
        self.id = id
        self.description = description
        self.filenames = filenames
        self.children = children
    
    def step_to_dictionary(self):
        """Convert Step instance to dictionary."""
        return {
            'id': self.id,
            'description': self.description,
            'filenames': self.filenames,
            'children': self.children,
        }

    def __repr__(self):
        """Return a string representation of the Step object."""
        return (f"Step(id='{self.id}', filenames={self.filenames}, description='{self.description}', children={self.children}")




def dictionary_to_step(dictionary):
    """Create Step instance from dictionary."""
    step = Step(dictionary['id'], dictionary['description'], dictionary['filenames'], dictionary['children'])
    return step