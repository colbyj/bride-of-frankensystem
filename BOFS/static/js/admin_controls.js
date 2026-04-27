// Behaviour for the admin/debug toolbar rendered by the adminControls macro.
// Loaded only when that macro is rendered (admin/debug + active participant).

(function () {
    // The toolbar is fixed-positioned. Reserve space at the bottom of the page
    // so content can scroll past it instead of being hidden underneath.
    function syncBodyPadding() {
        var toolbar = document.querySelector(".admin-toolbar");
        if (toolbar) {
            document.body.style.paddingBottom = toolbar.offsetHeight + "px";
        }
    }
    window.addEventListener("load", syncBodyPadding);
    window.addEventListener("resize", syncBodyPadding);

    // Restart confirmation. Bound on any element with [data-confirm-restart].
    document.addEventListener("click", function (event) {
        var target = event.target.closest("[data-confirm-restart]");
        if (!target) return;

        var ok = window.confirm(
            "Restart this session? All progress will be cleared, but you will stay logged in as admin."
        );
        if (!ok) {
            event.preventDefault();
        }
    });
})();
