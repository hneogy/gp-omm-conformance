import { pathToFileURL } from 'node:url';
const STUB = pathToFileURL(new URL('./cesium-stub.mjs', import.meta.url).pathname).href;
export async function resolve(specifier, context, next) {
  if (specifier === 'cesium') return { url: STUB, shortCircuit: true };
  return next(specifier, context);
}
