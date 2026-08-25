import { nodeProxyHandler } from './_serverProxy';

export default async function handler(req: any, res: any) {
  await nodeProxyHandler(req, res);
}