(function () {
    setInterval(function () {
        var xhr = new XMLHttpRequest();
        xhr.open("GET", "/user_active", true);
        xhr.send();
    }, 30000);
})();
