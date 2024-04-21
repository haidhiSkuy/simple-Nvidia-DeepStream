import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit
import numpy as np

# Define constants
ONNX_MODEL_PATH = "/workspaces/tes2/DeepstreamPython/model/yolox_s.onnx"
ENGINE_FILE_PATH = "/workspaces/tes2/DeepstreamPython/model/engines/yolox_s.engine"

# Initialize TensorRT logger
TRT_LOGGER = trt.Logger(trt.Logger.INFO)

# Create a TensorRT builder and network
builder = trt.Builder(TRT_LOGGER)
network_flags = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
network = builder.create_network(flags=network_flags)

# Create ONNX parser and parse the ONNX model
parser = trt.OnnxParser(network, TRT_LOGGER)
with open(ONNX_MODEL_PATH, 'rb') as model:
    if not parser.parse(model.read()):
        for error in range(parser.num_errors):
            print(parser.get_error(error))
        raise ValueError("Failed to parse ONNX model.")

# Configure builder parameters (e.g., precision mode, maximum batch size, etc.)
builder.max_workspace_size = 1 << 30  # 1 GB
builder.fp16_mode = True  # Enable FP16 precision mode

# Build TensorRT engine
engine = builder.build_cuda_engine(network)

# Serialize the engine to a file
with open(ENGINE_FILE_PATH, "wb") as f:
    f.write(engine.serialize())
