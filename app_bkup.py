from flask import Flask, request, render_template_string
import re

app = Flask(__name__)

def convert_capture_to_set(match):
    variable_name = match.group(1).strip()
    content = match.group(2).strip()
    return f"{{% set {variable_name} %}}{content}{{% endset %}}"

def convert_case_to_if_elif(match):
    case_variable = match.group(1).strip()
    contents = match.group(2).strip()
    when_clauses = re.split(r'{%\s*when\s+(.*?)\s*%}', contents)
    when_clauses = [w.strip() for w in when_clauses if w.strip()]
    else_clause = re.search(r'{%\s*else\s*%}(.+?){%\s*endcase\s*%}', contents, re.DOTALL)
    jinja_clauses = []
    for i in range(len(when_clauses)//2):
        condition = when_clauses[i*2].strip("'\"")
        jinja_clauses.append(f"{{% elif {case_variable} == {condition} %}}{when_clauses[i*2+1]}")
    if jinja_clauses:
        jinja_clauses[0] = jinja_clauses[0].replace('elif', 'if', 1)
    if else_clause:
        jinja_clauses.append(f"{{% else %}}{else_clause.group(1)}")
    jinja_clauses.append("{% endif %}")
    return '\n'.join(jinja_clauses)

def convert_variables_in_conditions(match):
    keyword = match.group(1)
    condition = match.group(2)
    condition = re.sub(r'\{\{\${(\w+)}\}\}', r'\1', condition)
    return f'{{% {keyword} {condition} %}}'

def convert_variables_in_loops(match):
    loop_variable = match.group(1)
    iterable = match.group(2)
    iterable = re.sub(r'\{\{\${(\w+)}\}\}', r'{{ \1 }}', iterable)
    return f'{{% for {loop_variable} in {iterable} %}}'

def remove_inner_double_curly_braces(match):
    # Retrieve the full matched text inside the {% and %}
    text_inside = match.group(0)
    # Remove only the {{ and }} inside the text, keeping the content inside them
    cleaned_text = re.sub(r'\{\{(.*?)\}\}', r'\1', text_inside)
    return cleaned_text

def convert_liquid_to_jinja(liquid_template):
    # Convert comments
    jinja_template = re.sub(r'{%-?\s*comment\s*-?%}(.+?){%-?\s*endcomment\s*-?%}', r'{# \1 #}', liquid_template, flags=re.DOTALL)
    
    # Convert conditions
    jinja_template = re.sub(r'{%\s*(if|elsif)\s+(.*?)\s*%}', convert_variables_in_conditions, jinja_template)
    
    # Convert loops
    jinja_template = re.sub(r'{%\s*for\s+(.*?)\s*in\s+(.*?)\s*%}', convert_variables_in_loops, jinja_template)
    
    # Convert the multiply (`times`) filter 
    jinja_template = re.sub(r'{%\s*assign\s+(\w+)\s*=\s*(\d+)\s*\|\s*times:\s*(\d+)\s*%}', r'{% set \1 = \2 * \3 %}', jinja_template)
    
    # Convert the truncate filter with indices first
    jinja_template = re.sub(r'{{\s*(\w+)\[(\d+)\]\s*\|\s*truncate:\s*(\d+)\s*}}', r'{{ \1[\2][:\3] }}', jinja_template)
    
    # Convert the truncate filter without indices
    jinja_template = re.sub(r'{{\s*(\w+)\s*\|\s*truncate:\s*(\d+)\s*}}',  r'{{ \1[:\2] }}', jinja_template)
    
    # Convert the split filter
    jinja_template = re.sub(r'{{\s*(\w+)\[(\d+)\]\s*\|\s*split\s*:\s*"([^"]+)"\s*}}', r'{{ \1[\2].split("\3") }}', jinja_template)
    jinja_template = re.sub(r'{{\s*(\w+)\s*\|\s*split\s*:\s*"([^"]+)"\s*}}', r'{{ \1.split("\2") }}', jinja_template)
    
    # Convert custom_attribute.${variable_name}
    jinja_template = re.sub(r'\{\{\s*custom_attribute\.\$\{(\w+)\}\s*\}\}', r"{{ UserAttribute['\1'] }}", jinja_template)

    jinja_template = re.sub(r'\{\{\s*campaign\.\$\{name\}\s*\}\}',r"{{ CampaignAttribute['c_n'] }}",jinja_template)
    
    # Convert general assign statements; this should be placed after the specific times and truncate ones
    jinja_template = re.sub(r'{%\s*assign\s+(\w+)\s*=(.*?)\s*%}', r'{% set \1 = \2 %}', jinja_template)

    # Convert case and capture blocks
    jinja_template = re.sub(r'{%\s*case\s+(.*?)\s*%}(.*?){%\s*endcase\s*%}', convert_case_to_if_elif, jinja_template, flags=re.DOTALL)
    jinja_template = re.sub(r'{%\s*capture\s+(\w+)\s*%}(.+?){%\s*endcapture\s*%}', convert_capture_to_set, jinja_template, flags=re.DOTALL)

    # Clean up variable references
    jinja_template = re.sub(r'{{\s*(\w+)\s*}}', r'{{ \1 }}', jinja_template)

    # Convert {{content_blocks.${variable_name}}}
    jinja_template = re.sub(r'\{\{\s*content_blocks\.\$\{(\w+)\}\s*\}\}',r"{{ ContentBlock['\1'] }}",jinja_template)

    # Fallback conversion for truncate filters (keep this as it worked)
    jinja_template = re.sub(r'\|\s*truncate:\s*(\d+)\s*%}', r'[:\1] %}', jinja_template)

    # Broader fallback conversion for any remaining assign statements
    jinja_template = re.sub(r'{%\s*assign\s+(.*?)\s*%}', r'{% set \1 %}', jinja_template)

    # Fallback for removing only {{ and }} inside {% ... %}
    jinja_template = re.sub(r'({%\s*.*?)(\{\{(.*?)\}\})(.*?\s*%})', r'\1\3\4', jinja_template)

    # Fallback for removing all {{ and }} inside {% ... %}
    # This will now call the remove_inner_curly_braces function for each match
    jinja_template = re.sub(r'{%.*?%}', remove_inner_double_curly_braces, jinja_template, flags=re.DOTALL)

    # Removal of | append: ""
    jinja_template = re.sub(r'\|\s*append:\s*""', '', jinja_template)

    # Removal of {% break %}
    jinja_template = re.sub(r'{%\s*break\s*%}', '', jinja_template)

    # Ensure final value is a string
    return jinja_template or ''


@app.route('/', methods=['GET', 'POST'])
def index():
    output_text = ''
    if request.method == 'POST':
        input_text = request.form['input_text']
        output_text = convert_liquid_to_jinja(input_text)  # Call the conversion function directly with form input
    return render_template_string(HOME_TEMPLATE, output=output_text)

HOME_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Conversion Tool</title>
</head>
<body>
    <h1>Liquid to Jinja2 Template Converter</h1>
    <form method="post">
        <textarea name="input_text" rows="10" cols="50" placeholder="Enter Liquid template here..."></textarea><br>
        <input type="submit" value="Convert">
    </form>
    {% if output %}
    <h2>Converted Jinja2 Template:</h2>
    <textarea rows="10" cols="50" readonly>{{ output }}</textarea>
    {% endif %}
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True)
