/*
 * Browser-side evaluator for the BOFS expression AST.
 *
 * Operates on the JSON AST produced by BOFS/expressions/parser.py. Mirrors
 * the Python evaluator's semantics — including Python-flavoured truthiness,
 * floor division, modulo, and `in`/`not_in` over both arrays and strings —
 * so a single AST evaluates identically on both sides of the wire.
 *
 * Exposes a single global `BOFSExpr` with .evaluate(ast, env, functions?).
 */
(function (root) {
    'use strict';

    // Python-flavoured truthiness: null/undefined/false/0/""/[] are falsy.
    function truthy(v) {
        if (v === null || v === undefined || v === false) return false;
        if (v === 0) return false;
        if (v === '') return false;
        if (Array.isArray(v) && v.length === 0) return false;
        return true;
    }

    function pyFloorDiv(a, b) {
        return Math.floor(a / b);
    }

    function pyMod(a, b) {
        // Python's % takes the sign of the divisor; JS's takes the sign of
        // the dividend. Re-anchor to match.
        return ((a % b) + b) % b;
    }

    function pyIn(needle, haystack) {
        if (Array.isArray(haystack)) {
            for (var i = 0; i < haystack.length; i++) {
                if (haystack[i] === needle) return true;
            }
            return false;
        }
        if (typeof haystack === 'string') {
            return haystack.indexOf(String(needle)) !== -1;
        }
        throw new Error("'in' requires a list or string on the right-hand side");
    }

    var FUNCS = {
        len: function (x) {
            if (x === null || x === undefined) {
                throw new Error("len() argument is null/undefined");
            }
            if (typeof x === 'string' || Array.isArray(x)) return x.length;
            throw new Error("len() requires a string or list");
        },
        min: function () {
            // min(iterable) or min(a, b, ...)
            var args = Array.prototype.slice.call(arguments);
            var values = (args.length === 1 && Array.isArray(args[0])) ? args[0] : args;
            if (values.length === 0) throw new Error("min() of empty sequence");
            return values.reduce(function (acc, v) { return v < acc ? v : acc; });
        },
        max: function () {
            var args = Array.prototype.slice.call(arguments);
            var values = (args.length === 1 && Array.isArray(args[0])) ? args[0] : args;
            if (values.length === 0) throw new Error("max() of empty sequence");
            return values.reduce(function (acc, v) { return v > acc ? v : acc; });
        },
        sum: function (xs, start) {
            if (!Array.isArray(xs)) throw new Error("sum() requires a list");
            var s = (start === undefined) ? 0 : start;
            for (var i = 0; i < xs.length; i++) s += xs[i];
            return s;
        },
        abs: function (x) { return Math.abs(x); },
        round: function (x, n) {
            if (n === undefined) return Math.round(x);
            var f = Math.pow(10, n);
            return Math.round(x * f) / f;
        },
        int: function (x) {
            var n = parseInt(x, 10);
            if (isNaN(n)) throw new Error("int(): cannot convert " + x);
            return n;
        },
        float: function (x) {
            var n = parseFloat(x);
            if (isNaN(n)) throw new Error("float(): cannot convert " + x);
            return n;
        },
        str: function (x) { return String(x); },
        bool: function (x) { return truthy(x); },
        mean: function (xs) {
            if (!Array.isArray(xs) || xs.length === 0) {
                throw new Error("mean() requires a non-empty list");
            }
            var s = 0;
            for (var i = 0; i < xs.length; i++) s += xs[i];
            return s / xs.length;
        },
        median: function (xs) {
            if (!Array.isArray(xs) || xs.length === 0) {
                throw new Error("median() requires a non-empty list");
            }
            var sorted = xs.slice().sort(function (a, b) { return a - b; });
            var mid = Math.floor(sorted.length / 2);
            return (sorted.length % 2)
                ? sorted[mid]
                : (sorted[mid - 1] + sorted[mid]) / 2;
        },
        stdev: function (xs) { return Math.sqrt(FUNCS.variance(xs)); },
        std: function (xs) { return Math.sqrt(FUNCS.variance(xs)); },
        variance: function (xs) {
            if (!Array.isArray(xs) || xs.length === 0) {
                throw new Error("variance() requires a non-empty list");
            }
            var m = FUNCS.mean(xs);
            var s = 0;
            for (var i = 0; i < xs.length; i++) {
                s += (xs[i] - m) * (xs[i] - m);
            }
            // Population variance (matches BOFS/util.var, which is pstdev-based).
            return s / xs.length;
        },
        var: function (xs) { return FUNCS.variance(xs); }
    };

    function evalNode(node, env, functions) {
        if (node === null || typeof node !== 'object') {
            throw new Error("malformed AST node: " + JSON.stringify(node));
        }

        if ('const' in node) return node['const'];

        if ('var' in node) {
            var name = node['var'];
            if (!(name in env)) {
                throw new Error("undefined variable: " + name);
            }
            return env[name];
        }

        if ('call' in node) {
            var fname = node['call'];
            if (!(fname in functions)) {
                throw new Error("function not available: " + fname);
            }
            var args = (node.args || []).map(function (a) {
                return evalNode(a, env, functions);
            });
            return functions[fname].apply(null, args);
        }

        if (!('op' in node)) {
            throw new Error("malformed AST node: " + JSON.stringify(node));
        }

        var op = node.op;
        var raw = node.args || [];

        // Short-circuit logical ops.
        if (op === 'and') {
            var lastA = true;
            for (var i = 0; i < raw.length; i++) {
                lastA = evalNode(raw[i], env, functions);
                if (!truthy(lastA)) return lastA;
            }
            return lastA;
        }
        if (op === 'or') {
            var lastO = false;
            for (var j = 0; j < raw.length; j++) {
                lastO = evalNode(raw[j], env, functions);
                if (truthy(lastO)) return lastO;
            }
            return lastO;
        }
        if (op === 'if') {
            if (raw.length !== 3) {
                throw new Error("'if' expects exactly 3 arguments");
            }
            var test = evalNode(raw[0], env, functions);
            return evalNode(truthy(test) ? raw[1] : raw[2], env, functions);
        }

        var values = raw.map(function (a) { return evalNode(a, env, functions); });

        if (op === 'list') return values;
        if (op === 'not') return !truthy(values[0]);
        if (op === 'neg') return -values[0];
        if (op === 'pos') return +values[0];

        if (values.length !== 2) {
            throw new Error("operator '" + op + "' expects 2 arguments");
        }
        var a = values[0], b = values[1];

        switch (op) {
            case '+':
                // Match Python: string + string = concat; number + number = sum.
                if (typeof a === 'string' || typeof b === 'string') {
                    return String(a) + String(b);
                }
                return a + b;
            case '-': return a - b;
            case '*': return a * b;
            case '/': return a / b;
            case '//': return pyFloorDiv(a, b);
            case '%': return pyMod(a, b);
            case '<': return a < b;
            case '<=': return a <= b;
            case '>': return a > b;
            case '>=': return a >= b;
            case '==': return a === b;
            case '!=': return a !== b;
            case 'in': return pyIn(a, b);
            case 'not_in': return !pyIn(a, b);
            default: throw new Error("unknown operator: " + op);
        }
    }

    function evaluate(node, env, functions) {
        return evalNode(node, env || {}, functions || FUNCS);
    }

    var api = {
        evaluate: evaluate,
        defaultFunctions: function () { return FUNCS; },
        truthy: truthy
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    } else {
        root.BOFSExpr = api;
    }
}(typeof self !== 'undefined' ? self : this));
