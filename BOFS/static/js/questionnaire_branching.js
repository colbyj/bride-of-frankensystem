/*
 * Conditional question display ("show_if") for BOFS questionnaires.
 *
 * Each question whose JSON definition includes a `show_if` predicate is
 * rendered with class="bofs-conditional" and a `data-show-if` attribute
 * holding the parsed AST as JSON. On page load this script extracts the
 * referenced field IDs from each AST, attaches change/input listeners to
 * those inputs, and toggles the question's `.bofs-hidden` class plus any
 * `required`/`disabled` state on its inputs whenever the predicate flips.
 *
 * Depends on bofs_expressions.js providing window.BOFSExpr.
 */
(function () {
    'use strict';

    if (typeof window.BOFSExpr === 'undefined') {
        console.error('BOFS branching: bofs_expressions.js is not loaded.');
        return;
    }

    var truthy = window.BOFSExpr.truthy;
    var conditionals = [];        // {el, ast, fields}
    var fieldIndex = {};          // fieldId -> [conditional, ...]

    function collectVarNames(node, out) {
        if (!node || typeof node !== 'object') return;
        if ('var' in node) {
            out[node['var']] = true;
            return;
        }
        if ('args' in node) {
            for (var i = 0; i < node.args.length; i++) {
                collectVarNames(node.args[i], out);
            }
        }
    }

    function readFieldValue(fieldId) {
        // Radio: value of the checked option in the group.
        var checkedRadio = document.querySelector(
            'input[type="radio"][name="' + cssEscape(fieldId) + '"]:checked'
        );
        if (checkedRadio) return coerce(checkedRadio.value);

        // If a radio group exists but none are checked, return undefined.
        var anyRadio = document.querySelector(
            'input[type="radio"][name="' + cssEscape(fieldId) + '"]'
        );
        if (anyRadio) return undefined;

        // Single checkbox: boolean.
        var anyCheckbox = document.querySelector(
            'input[type="checkbox"][name="' + cssEscape(fieldId) + '"]'
        );
        if (anyCheckbox) {
            // If multiple checkboxes share the name (rare here), return list of
            // checked values; otherwise the boolean state.
            var allCheckboxes = document.querySelectorAll(
                'input[type="checkbox"][name="' + cssEscape(fieldId) + '"]'
            );
            if (allCheckboxes.length > 1) {
                var picked = [];
                for (var i = 0; i < allCheckboxes.length; i++) {
                    if (allCheckboxes[i].checked) picked.push(coerce(allCheckboxes[i].value));
                }
                return picked;
            }
            return anyCheckbox.checked;
        }

        // Anything else: text input, textarea, select.
        var input = document.querySelector('[name="' + cssEscape(fieldId) + '"]');
        if (input) return coerce(input.value);

        return undefined;
    }

    function coerce(v) {
        if (v === '' || v === null || v === undefined) return v;
        if (typeof v !== 'string') return v;
        // Numeric strings → numbers, so age comparisons work as expected.
        if (/^-?\d+(\.\d+)?$/.test(v)) {
            var n = Number(v);
            if (!isNaN(n)) return n;
        }
        return v;
    }

    // CSS.escape polyfill for older browsers; field IDs in the wild include
    // characters that ``querySelector`` would otherwise mis-parse.
    var cssEscape = (window.CSS && window.CSS.escape)
        ? window.CSS.escape.bind(window.CSS)
        : function (s) {
            return String(s).replace(/[^a-zA-Z0-9_-]/g, function (c) {
                return '\\' + c;
            });
        };

    function buildEnv(fields) {
        var env = {};
        for (var i = 0; i < fields.length; i++) {
            env[fields[i]] = readFieldValue(fields[i]);
        }
        return env;
    }

    function applyVisibility(cond) {
        var env = buildEnv(cond.fields);
        var visible;
        try {
            visible = truthy(window.BOFSExpr.evaluate(cond.ast, env));
        } catch (e) {
            // An undefined variable is normal during early renders — treat
            // as "not yet visible" rather than blowing up the page.
            visible = false;
        }
        if (visible) {
            cond.el.classList.remove('bofs-hidden');
            restoreRequired(cond.el);
        } else {
            cond.el.classList.add('bofs-hidden');
            suppressRequired(cond.el);
        }
    }

    // When a question is hidden, remove `required` from any inputs inside
    // so HTML5 validation does not block form submission. Stash the original
    // state on a data attribute so we can put it back when the question
    // becomes visible again.
    function suppressRequired(el) {
        var inputs = el.querySelectorAll('input, select, textarea');
        for (var i = 0; i < inputs.length; i++) {
            var node = inputs[i];
            if (node.hasAttribute('required') && !node.hasAttribute('data-bofs-was-required')) {
                node.setAttribute('data-bofs-was-required', '1');
                node.removeAttribute('required');
            }
        }
    }

    function restoreRequired(el) {
        var inputs = el.querySelectorAll('[data-bofs-was-required]');
        for (var i = 0; i < inputs.length; i++) {
            inputs[i].setAttribute('required', '');
            inputs[i].removeAttribute('data-bofs-was-required');
        }
    }

    function setup() {
        var nodes = document.querySelectorAll('.bofs-conditional[data-show-if]');
        for (var i = 0; i < nodes.length; i++) {
            var raw = nodes[i].getAttribute('data-show-if');
            if (!raw) continue;
            var ast;
            try {
                ast = JSON.parse(raw);
            } catch (e) {
                console.error('BOFS branching: bad data-show-if JSON', raw);
                continue;
            }
            var varNames = {};
            collectVarNames(ast, varNames);
            var fields = Object.keys(varNames);
            var cond = {el: nodes[i], ast: ast, fields: fields};
            conditionals.push(cond);
            for (var f = 0; f < fields.length; f++) {
                if (!fieldIndex[fields[f]]) fieldIndex[fields[f]] = [];
                fieldIndex[fields[f]].push(cond);
            }
        }

        // Single delegated listener — works for inputs added later too.
        document.addEventListener('change', onFieldEvent, true);
        document.addEventListener('input', onFieldEvent, true);

        // Initial pass: hide questions whose predicate is false on load.
        for (var k = 0; k < conditionals.length; k++) {
            applyVisibility(conditionals[k]);
        }
    }

    function onFieldEvent(evt) {
        var target = evt.target;
        if (!target || !target.name) return;
        var dependents = fieldIndex[target.name];
        if (!dependents) return;
        for (var i = 0; i < dependents.length; i++) {
            applyVisibility(dependents[i]);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setup);
    } else {
        setup();
    }
}());
