const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[2], "utf8");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const context = vm.createContext({Date});
vm.runInContext(source, context, {timeout: 5000});
context.input = input;
process.stdout.write(JSON.stringify(vm.runInContext("main(input)", context, {timeout: 5000})));
