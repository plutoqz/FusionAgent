from utils.local_runtime import apply_runtime_entrypoint_defaults

apply_runtime_entrypoint_defaults()

from api.app import create_app


app = create_app()
