document.addEventListener("DOMContentLoaded", function () {
    const menu_button = document.getElementById("menu");
    const nav_links = document.getElementById("nav-links-mobile");

    menu_button.addEventListener("click", function () {
        if (menu_button.classList.contains("active")) {
            menu_button.classList.remove("active")
            nav_links.classList.remove("active")
        } else {
            menu_button.classList.add("active")
            nav_links.classList.add("active")
        }
    })
})