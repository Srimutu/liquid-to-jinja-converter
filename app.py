from flask import Flask, request, render_template_string
import re
import json
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


def preprocess_input(liquid_template, replacements_json):
    try:
        replacements = json.loads(replacements_json)
    except json.JSONDecodeError:
        return liquid_template  # Return the original template if JSON is invalid
    
    for key, value in replacements.items():
        liquid_template = liquid_template.replace(key, value)
    
    return liquid_template

@app.route('/', methods=['GET', 'POST'])
def index():
    output_text = ''
    input_text = ''
    if request.method == 'POST':
        input_text = request.form['input_text']
        replacements_json = request.form.get('replacements_json', '{}')  # Default to empty JSON if not provided
        preprocessed_input = preprocess_input(input_text, replacements_json)
        output_text = convert_liquid_to_jinja(preprocessed_input)  # Use the preprocessed input for conversion
    return render_template_string(HOME_TEMPLATE, output=output_text,input_text=input_text)

HOME_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <!-- Google Tag Manager -->
    <script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
    new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
    j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
    'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
    })(window,document,'script','dataLayer','GTM-N8TK26VN');</script>
    <!-- End Google Tag Manager -->
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Liquid to Jinja Converter</title>
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootswatch/4.5.2/lux/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css">
<style>
    .code-input, .code-output {
        height: 50vh !important;
    }

    .copy-icon {
        position: relative;
        margin-top: 10px;
        cursor: pointer;
        color: #000;
        font-size: 24px;
    }

    #convertButton {
        display: block;
        margin: 20px auto;
        width: fit-content;
    }

    /* Dark mode background and color */

    .dark-mode {
        background-color: #1a1a1a;
        color: #fff;
        position: relative;
        overflow: hidden;
    }

    .dark-mode h1 {
        color: #fff;
    }

    .dark-mode .code-input,
    .dark-mode .code-output {
        background-color: #333;
        color: #fff;
    }

    .dark-mode .btn-primary {
        background-color: #4b4b4b;
        border-color: #4b4b4b;
    }

    .dark-mode .copy-icon {
        color: #fff;
    }

    .dark-mode::before {
        content: ' ';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: transparent;
    }

#starry-night {
  position: relative;
  width: 100%;
  height: 100%;
  background: transparent;
}

.star {
  position: absolute;
  background-color: white;
  border-radius: 50%;
  opacity: 0;
  animation: twinkle 2s infinite ease-in-out;
}

/* Keyframes for twinkle effect */
@keyframes twinkle {
  0%, 100% {
    opacity: 0;
  }
  50% {
    opacity: 1;
  }
}

</style>
</head>
<body>
    <!-- Google Tag Manager (noscript) -->
    <noscript>
        <iframe src="https://www.googletagmanager.com/ns.html?id=GTM-N8TK26VN"
        height="0" width="0" style="display:none;visibility:hidden"></iframe>
    </noscript>
    <!-- End Google Tag Manager (noscript) -->
  <div id="starry-night"></div>

    <div class="container mt-4">
        <h1 class="text-center">Liquid to Jinja2 Template Converter</h1>
        <form method="post">
            <div class="row">
                <div class="col-md-6">
                    <textarea name="input_text" id="LiquidInput" class="form-control code-input" placeholder="Enter Liquid template here...">{% if input_text %}{{ input_text }}{% endif %}</textarea>
                </div>
                <div class="col-md-6">
                    <textarea id="jinjaOutput" class="form-control code-output" placeholder="Jinja output will appear here" readonly>{{ output }}</textarea>
                </div>
            </div>
            <div class="row">
                <div class="col-12">
                    <label for="replacementsJson">Replacements JSON:</label>
                    <textarea name="replacements_json" id="replacementsJson" class="form-control" placeholder='Enter search and replace JSON here...'></textarea>
              </div>
            </div>
            <div class="row">
                <div class="col-12 text-center mt-3">
                    <button id="convertButton" class="btn btn-primary">Convert</button>
                </div>
            </div>
        </form>
        <div class="row">
            <div class="col-12 text-center mt-3">
                <i class="fas fa-copy copy-icon" onclick="copyToClipboard()"></i>
                <i id="toggleDarkMode" class="fas fa-moon ml-2" style="font-size: 24px; cursor: pointer;"></i>
            </div>
        </div>
    </div>

    <script type="text/javascript">        
    var darkModeIcon = document.getElementById('toggleDarkMode');

        darkModeIcon.addEventListener('click', function() {
            document.body.classList.toggle('dark-mode');
            if (document.body.classList.contains('dark-mode')) {
                darkModeIcon.classList.remove('fa-moon');
                darkModeIcon.classList.add('fa-sun');
            } else {
                darkModeIcon.classList.remove('fa-sun');
                darkModeIcon.classList.add('fa-moon');
            }
        });

        function copyToClipboard() {
            var jinjaOutputTextarea = document.getElementById('jinjaOutput');
            jinjaOutputTextarea.select();
            document.execCommand('copy');
        }</script>
<script>
// stars
document.addEventListener("DOMContentLoaded", function() {
  const starryNight = document.getElementById('starry-night');

  // Function to generate random values
  function getRandomValue(min, max) {
    return Math.random() * (max - min) + min;
  }

  // Function to create a single star
  function createStar() {
    const star = document.createElement('div');
    star.classList.add('star');
    star.style.width = `${getRandomValue(1, 3)}px`;
    star.style.height = star.style.width;
    star.style.top = `${getRandomValue(0, window.innerHeight)}px`;
    star.style.left = `${getRandomValue(0, window.innerWidth)}px`;
    star.style.animationDuration = `${getRandomValue(0.5, 1.5)}s`;
    star.style.animationDelay = `${getRandomValue(0, 2)}s`;
    starryNight.appendChild(star);
  }

  // Function to create multiple stars
  function createStars(count) {
    for(let i = 0; i < count; i++) {
      createStar();
    }
  }

  // Generate 1000 stars
  createStars(15);
});
</script>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True)
