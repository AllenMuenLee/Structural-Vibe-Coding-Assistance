import json
from Flowchart import Flowchart
from ai_helper import generate_flowchart_from_description


def main():
    """
    Main function to run the vibe coding app.
    """

    project_name = "project_1"
    
    print("=== Vibe Coding App ===")
    print()
    
    # Step 1: Get user input
    print("Describe your task:")
    task_description = input("> ")
    print()
    
    # Step 2: Generate flowchart from AI
    print("Generating flowchart with AI...")
    
    ai_data = generate_flowchart_from_description(task_description, project_name)
    print("✓ AI generated flowchart structure")
    print()
    
    print(ai_data)
    
    # Step 3: Create Flowchart object with name and framework
    framework = ai_data.get('framework', '')  # Get framework from AI response
    command = ai_data.get('COMMAND', '')  # Get command from AI response
    my_flowchart = Flowchart(name=task_description, framework=framework, project_name=project_name)
    my_flowchart.create_from_ai_response(ai_data)
    print("✓ Flowchart created")
    print()
    
    # Step 4: Save to JSON file
    filename = "flowchart.json"
    my_flowchart.save_to_file(my_flowchart.project_name + '/' +filename)
    print(f"✓ Saved to {filename}")
    print()
    
    # Step 5: Show the flowchart
    print("=== Your Flowchart ===")
    flowchart_dict = my_flowchart.flowchart_to_dictionary()
    print(json.dumps(flowchart_dict, indent=2))


# Run the program
if __name__ == "__main__":
    main()