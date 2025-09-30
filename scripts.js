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
        }
