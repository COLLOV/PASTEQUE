const { inspect } = require('node:util');

function formatArgs(args) {
  return args
    .map(arg => {
      if (typeof arg === 'string') return arg;
      try {
        return inspect(arg, { depth: 3, colors: false });
      } catch {
        return String(arg);
      }
    })
    .join(' ');
}

const write = data => {
  try {
    process.stderr.write(`${data}\n`);
  } catch {
    // swallow logging failures silently
  }
};

['log', 'info', 'debug'].forEach(method => {
  const original = console[method].bind(console);
  console[method] = (...args) => {
    const [first] = args;
    if (typeof first === 'string') {
      const trimmed = first.trimStart();
      if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
        return original(...args);
      }
    }
    write(formatArgs(args));
    return undefined;
  };
});
