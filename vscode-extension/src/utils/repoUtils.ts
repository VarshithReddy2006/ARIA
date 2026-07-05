export function splitRepo(identifier: string): [string, string] {
  const parts = identifier.split('/');
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    throw new Error(`Invalid repository identifier "${identifier}". Expected "owner/repo".`);
  }
  return [parts[0], parts[1]];
}
