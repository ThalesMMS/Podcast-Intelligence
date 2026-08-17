"use strict";

const safeBraceExpansion = require("brace-expansion-safe");

module.exports = safeBraceExpansion.expand;
Object.assign(module.exports, safeBraceExpansion);
