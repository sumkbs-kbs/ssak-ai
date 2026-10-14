import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const run = path.dirname(fileURLToPath(import.meta.url));
const hash = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const modules = JSON.parse(fs.readFileSync(path.join(run, 'module-bindings.json'), 'utf8'));
if (!modules.every((module) => hash(module.path) === module.sha256)) throw new Error('Module binding changed');
const files = fs.readdirSync(run, { recursive: true }).filter((file) => fs.statSync(path.join(run, file)).isFile() && file !== 'artifact-manifest.json');
const manifest = files.map((file) => ({ file, bytes: fs.statSync(path.join(run, file)).size, sha256: hash(path.join(run, file)) }));
fs.writeFileSync(path.join(run, 'artifact-manifest.json'), JSON.stringify(manifest, null, 2));
console.log(JSON.stringify({ artifacts: manifest.length, bytes: manifest.reduce((sum, item) => sum + item.bytes, 0), modulesVerified: modules.length }));
