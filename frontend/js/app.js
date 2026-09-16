function toggleTheme(){document.body.classList.toggle("dark");localStorage.setItem("aditya-theme",document.body.classList.contains("dark")?"dark":"light")}
if(localStorage.getItem("aditya-theme")==="dark")document.body.classList.add("dark");
