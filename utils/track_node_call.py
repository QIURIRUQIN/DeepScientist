from loguru import logger
import os
import json

from langchain_core.load import dumps

from utils.state import State

def track_node_call(subgraph_name: str = ""):
    def track_node_call_inner(func):
        node_name = f"subgraph_{subgraph_name}.{func.__name__}"

        def skip_func(state: State, **kwargs):
            logger.info(f"Skiping {node_name}")
            return state
        
        def wrapper(state: State, **kwargs):
            latest_state_path = os.path.join(state['save_path'], "latest_state.json")
            with open(latest_state_path, "w") as f:
                f.write(dumps(state, ensure_ascii=False, indent=4))

            if state is not None:
                if ("node_call_stack" not in state) or (not isinstance(state["node_call_stack"], list)):
                    state["node_call_stack"] = []

                node_call_stack_path = os.path.join(state['save_path'], 'node_call_stack.json')
                with open(node_call_stack_path, 'w') as f:
                    f.write(json.dumps(state['node_call_stack'], indent=4))

                if ("resume_node_call_stack" in state) and state["resume_node_call_stack"]:
                        if node_name != state["resume_node_call_stack"][-1]:
                            return skip_func(state, **kwargs)

                state["resume_node_call_stack"] = []
                logger.info(f"Calling node: {node_name}")

            return func(state, **kwargs)

        return wrapper
    return track_node_call_inner
