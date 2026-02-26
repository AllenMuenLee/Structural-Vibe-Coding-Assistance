from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    """
    Render the index page.
    """
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)

from flask import Flask, render_template, request

app = Flask(__name__)

@app.route('/')
def index():
    """
    Render the index page.
    """
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    """
    Perform calculation based on input from the form.
    """
    try:
        num1 = float(request.form['num1'])
        num2 = float(request.form['num2'])
        operation = request.form['operation']

        if operation == 'add':
            result = num1 + num2
        elif operation =='subtract':
            result = num1 - num2
        elif operation =='multiply':
            result = num1 * num2
        elif operation == 'divide':
            if num2!= 0:
                result = num1 / num2
            else:
                return "Error: Division by zero is not allowed."
        else:
            return "Error: Invalid operation"

        return render_template('index.html', result=result)
    except ValueError:
        return "Error: Invalid input"

if __name__ == '__main__':
    app.run(debug=True)

