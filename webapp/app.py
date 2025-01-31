
import collections.abc
import io
from itertools import islice
from flask import Flask, request, render_template_string
import jsonpickle
from search import binary_search
import monitor

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request is not None and isinstance(request, collections.abc.Iterable):
        print(jsonpickle.encode(request.__dict__))
    else:
        print("not iter", request)
    html_form = """
    <html>
      <body>
        <h2>Enter an ordered list (comma-separated) and a key to search :</h2>
        <form method="POST">
          <label for="arr">Ordered List (e.g. 1,2,3,4):</label><br>
          <input type="text" id="arr" name="arr" required><br><br>
          <label for="key">Key to Search:</label><br>
          <input type="text" id="key" name="key" required><br><br>
          <input type="submit" value="Search">
        </form>
      </body>
    </html>
    """

    if request.method == 'POST':
        # Retrieve data from the form
        arr_str = request.form.get('arr', '')
        key_str = request.form.get('key', '')

        # Convert arr_str into a list of integers
        try:
            arr = [int(x.strip()) for x in arr_str.split(',')]
        except ValueError:
            return "Invalid list input, please enter integers separated by commas."

        # Convert the key to integer
        try:
            key = int(key_str)
        except ValueError:
            return "Invalid key input, please enter a valid integer."

        # Call the binary search function
        found = binary_search(arr, key)

        # Display result
        html_result = f"""
        <html>
          <body>
            <h3>Array: {arr}</h3>
            <h3>Key: {key}</h3>
            <h3>Found? {found}</h3>
            <a href="/">Go Back</a>
          </body>
        </html>
        """
        return render_template_string(html_result)

    # If it's a GET request, just show the form
    return render_template_string(html_form)



if __name__ == "__main__":
    app.run(debug=True) 