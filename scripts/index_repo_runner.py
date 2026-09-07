import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.dependencies import (
    get_architecture_service,
    get_symbol_service,
    get_call_graph_service,
    get_api_surface_service,
)

repo_name = sys.argv[1] if len(sys.argv) > 1 else "psf/requests"
local_dir = sys.argv[2] if len(sys.argv) > 2 else "data/cloned_repos/psf_requests"
repo_path = os.path.abspath(local_dir)

print(f"Indexing {repo_name} from {repo_path}...")

arch_svc = get_architecture_service()
res_arch = arch_svc.build(repo_name, repo_path=repo_path)
print(
    f"Architecture: {res_arch['files_parsed']} files parsed, {res_arch['dependencies_found']} dependencies."
)

sym_svc = get_symbol_service()
res_sym = sym_svc.build(repo_name, repo_path=repo_path)
print(
    f"Symbols: {res_sym.get('symbol_count', 0)} symbols in {res_sym.get('files_indexed', 0)} files."
)

cg_svc = get_call_graph_service()
gen_cg = cg_svc.build(repo_name)
res_cg = None
try:
    while True:
        next(gen_cg)
except StopIteration as e:
    res_cg = e.value
print(f"Call Graph: {res_cg.node_count} nodes, {res_cg.edge_count} edges.")

api_svc = get_api_surface_service()
gen_api = api_svc.build(repo_name)
res_api = None
try:
    while True:
        next(gen_api)
except StopIteration as e:
    res_api = e.value
print(
    f"API Surface: {res_api.stats.total_symbols} symbols, {res_api.stats.public_count} public."
)
print("INDEXING COMPLETE!")
