import { nodeProxyHandler } from '../src/lib/serverProxy.ts';

export default async function handler(req, res) {
  return nodeProxyHandler(req, res);
}
