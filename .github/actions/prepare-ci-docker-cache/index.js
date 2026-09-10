const fs = require('node:fs');

// GITHUB_TOKEN/registry credential, 전체 environment와 runtime 값은 출력하지 않는다.
const keys = ['ACTIONS_RUNTIME_TOKEN', 'ACTIONS_RESULTS_URL'];
const ready = keys.every((key) => process.env[key] && !/[\x00-\x1f\x7f]/.test(process.env[key]))
  && process.env.ACTIONS_RESULTS_URL.startsWith('https://');
try {
  if (ready && process.env.GITHUB_ENV && process.env.GITHUB_OUTPUT) {
    fs.appendFileSync(process.env.GITHUB_ENV, keys.map((key) => `${key}=${process.env[key]}\n`).join(''));
    fs.appendFileSync(process.env.GITHUB_OUTPUT, 'ready=true\n');
  } else if (process.env.GITHUB_OUTPUT) {
    fs.appendFileSync(process.env.GITHUB_OUTPUT, 'ready=false\n');
  }
} catch {
  // continue-on-error와 build helper가 원래 검증을 수행한다. 예외에 경로/값을 노출하지 않는다.
  process.exitCode = 1;
}
