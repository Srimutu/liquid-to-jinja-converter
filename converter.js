/**
 * @file converter.js
 * @description Consolidated script to handle Liquid to Jinja conversion,
 * UI logic (copy, dark mode), and star background effects
 * entirely in the browser (client-side).
 */

document.addEventListener("DOMContentLoaded", function() {
    // === 1. CORE CONVERSION LOGIC (PYTHON PORT) ===

    // Helper to convert Liquid capture blocks to Jinja set/endset
    function convertCaptureToSet(match, variableName, content) {
        return `{% set ${variableName.trim()} %}${content.trim()}{% endset %}`;
    }

    // Helper to convert Liquid case/when blocks to Jinja if/elif/else
    function convertCaseToIfElif(match, caseVariable, contents) {
        const variable = caseVariable.trim();
        // Regex to split contents by {% when ... %}
        const whenClauses = contents.split(/{%\s*when\s+(.*?)\s*%}/g).filter(w => w.trim());
        
        // Find the optional else clause
        const elseMatch = contents.match(/{%\s*else\s*%}(.+?){%\s*endcase\s*%}/s);
        
        let jinjaClauses = [];

        for (let i = 0; i < whenClauses.length; i += 2) {
            if (i + 1 < whenClauses.length) {
                const condition = whenClauses[i].trim().replace(/['"]/g, ''); // Extract condition value
                const content = whenClauses[i + 1];

                if (i === 0) {
                    // First condition uses 'if'
                    jinjaClauses.push(`{% if ${variable} == ${condition} %}${content}`);
                } else {
                    // Subsequent conditions use 'elif'
                    jinjaClauses.push(`{% elif ${variable} == ${condition} %}${content}`);
                }
            }
        }

        if (elseMatch) {
            jinjaClauses.push(`{% else %}${elseMatch[1].trim()}`);
        }
        
        jinjaClauses.push("{% endif %}");
        
        return jinjaClauses.join('\n');
    }

    // Helper to remove inner curly braces from Jinja tags (e.g., {% if {{val}} %} -> {% if val %})
    function removeInnerDoubleCurlyBraces(match) {
        // match[0] is the whole {% ... %} tag
        // Replace inner {{...}} with just the content inside
        return match[0].replace(/\{\{(.*?)\}\}/g, (m, content) => content.trim());
    }

    // Main conversion function (Port of convert_liquid_to_jinja)
    function convertLiquidToJinja(liquidTemplate, replacements) {
        let jinjaTemplate = liquidTemplate;

        // Apply pre-processing replacements
        for (const [key, value] of Object.entries(replacements)) {
            jinjaTemplate = jinjaTemplate.split(key).join(value);
        }

        // --- DIRECT REGEX CONVERSIONS (Order matters!) ---

        // 1. Convert comments
        jinjaTemplate = jinjaTemplate.replace(/{%-?\s*comment\s*-?%}(.+?){%-?\s*endcomment\s*-?%}/gs, '{# $1 #}');

        // 2. Convert multiply filter: assign var = val | times: num  -> set var = val * num
        // Simplified for string replacement accuracy on whole block
        jinjaTemplate = jinjaTemplate.replace(/{%\s*assign\s+(\w+)\s*=\s*(\d+)\s*\|\s*times:\s*(\d+)\s*%}/g, '{% set $1 = $2 * $3 %}');
        
        // 3. Convert custom_attribute.${variable_name} to Jinja dictionary access
        jinjaTemplate = jinjaTemplate.replace(/\{\{\s*custom_attribute\.\$\{(\w+)\}\s*\}\}/g, "{{ UserAttribute['$1'] }}");
        
        // 4. Convert specific Braze attributes (campaign name)
        jinjaTemplate = jinjaTemplate.replace(/\{\{\s*campaign\.\$\{name\}\s*\}\}/g, "{{ CampaignAttribute['c_n'] }}");

        // 5. Convert content_blocks
        jinjaTemplate = jinjaTemplate.replace(/\{\{\s*content_blocks\.\$\{(\w+)\}\s*\}\}/g, "{{ ContentBlock['$1'] }}");
        
        // 6. Convert split filter (with and without array index)
        jinjaTemplate = jinjaTemplate.replace(/\{\{\s*(\w+)\[(\d+)\]\s*\|\s*split\s*:\s*"([^"]+)"\s*\}\}/g, '{{ $1[$2].split("$3") }}');
        jinjaTemplate = jinjaTemplate.replace(/\{\{\s*(\w+)\s*\|\s*split\s*:\s*"([^"]+)"\s*\}\}/g, '{{ $1.split("$2") }}');

        // 7. Convert truncate filter (with and without array index) to Python slice syntax
        // NOTE: Jinja filters are usually better, but slicing is a direct Liquid to Python conversion.
        jinjaTemplate = jinjaTemplate.replace(/\{\{\s*(\w+)\[(\d+)\]\s*\|\s*truncate:\s*(\d+)\s*\}\}/g, '{{ $1[$2][: $3] }}');
        jinjaTemplate = jinjaTemplate.replace(/\{\{\s*(\w+)\s*\|\s*truncate:\s*(\d+)\s*\}\}/g, '{{ $1[: $2] }}');

        // 8. Convert general assign statements (MUST be after specific assignments like times)
        jinjaTemplate = jinjaTemplate.replace(/{%\s*assign\s+(\w+)\s*=(.*?)\s*%}/g, '{% set $1 = $2 %}');
        
        // 9. Convert case/when blocks (Complex logic - uses helper function)
        jinjaTemplate = jinjaTemplate.replace(/{%\s*case\s+(.*?)\s*%}(.*?){%\s*endcase\s*%}/gs, convertCaseToIfElif);
        
        // 10. Convert capture blocks (Complex logic - uses helper function)
        jinjaTemplate = jinjaTemplate.replace(/{%\s*capture\s+(\w+)\s*%}(.+?){%\s*endcapture\s*%}/gs, convertCaptureToSet);
        
        // 11. Convert Liquid variable access in if/for statements to Jinja syntax (remove ${{...}} and {{...}})
        // {% if {{${variable}}} == 'value' %} -> {% if variable == 'value' %}
        jinjaTemplate = jinjaTemplate.replace(/{%\s*(if|elsif)\s+(.*?)\s*%}/g, (match, keyword, condition) => {
            let cleanCondition = condition.replace(/\{\{\s*\$\{(\w+)\}\s*\}\}/g, '$1');
            return `{% ${keyword} ${cleanCondition} %}`;
        });
        
        // {% for loop_var in {{${iterable}}} %} -> {% for loop_var in iterable %}
        jinjaTemplate = jinjaTemplate.replace(/{%\s*for\s+(.*?)\s*in\s+(.*?)\s*%}/g, (match, loopVar, iterable) => {
            let cleanIterable = iterable.replace(/\{\{\s*\$\{(\w+)\}\s*\}\}/g, '$1');
            return `{% for ${loopVar.trim()} in ${cleanIterable.trim()} %}`;
        });
        
        // 12. Fallback: Remove all {{...}} inside {% ... %} tags that might have slipped through
        jinjaTemplate = jinjaTemplate.replace(/{%.*?%}/gs, removeInnerDoubleCurlyBraces);

        // 13. Remove specific Liquid-isms that aren't necessary in Jinja
        jinjaTemplate = jinjaTemplate.replace(/\|\s*append:\s*""/g, ''); // Remove | append: ""
        jinjaTemplate = jinjaTemplate.replace(/{%\s*break\s*%}/g, ''); // Remove {% break %}

        // 14. Clean up generic liquid variables {{ ${variable} }} or {{ variable }} -> {{ variable }}
        jinjaTemplate = jinjaTemplate.replace(/\{\{\s*\$\{(\w+)\}\s*\}\}/g, '{{ $1 }}');

        // 15. Standardize Liquid's generic {{ variable }} to Jinja's {{ variable }}
        // This should be one of the last steps
        jinjaTemplate = jinjaTemplate.replace(/\{\{\s*(\w+)\s*\}\}/g, '{{ $1 }}');
        
        return jinjaTemplate;
    }

    // === 2. UI HANDLERS AND EVENT LISTENERS ===

    const form = document.querySelector('form');
    const inputTextArea = document.getElementById('LiquidInput');
    const outputTextArea = document.getElementById('jinjaOutput');
    const replacementsJsonArea = document.getElementById('replacementsJson');
    const darkModeIcon = document.getElementById('toggleDarkMode');
    const copyIcon = document.querySelector('.fa-copy');

    // Prevent default form submission and run conversion directly
    form.addEventListener('submit', function(e) {
        e.preventDefault();

        const liquidInput = inputTextArea.value;
        const jsonInput = replacementsJsonArea.value || '{}';
        let replacements = {};
        
        try {
            replacements = JSON.parse(jsonInput);
        } catch (error) {
            outputTextArea.value = "Error: Invalid JSON in the Replacements box.";
            return;
        }

        const jinjaOutput = convertLiquidToJinja(liquidInput, replacements);
        outputTextArea.value = jinjaOutput;
    });

    // Dark Mode Toggle Logic
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

    // Copy to Clipboard Logic
    copyIcon.addEventListener('click', function() {
        outputTextArea.select();
        document.execCommand('copy');
        // Simple visual feedback
        copyIcon.classList.remove('fa-copy');
        copyIcon.classList.add('fa-check');
        setTimeout(() => {
            copyIcon.classList.remove('fa-check');
            copyIcon.classList.add('fa-copy');
        }, 1000);
    });

    // === 3. STAR BACKGROUND EFFECT ===
    // This logic is retained from the original HTML template for visual effect
    const starryNight = document.getElementById('starry-night');
    function getRandomValue(min, max) {
        return Math.random() * (max - min) + min;
    }

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
    
    // Generate 15 stars (retains original star count)
    for(let i = 0; i < 15; i++) {
        createStar();
    }
});
