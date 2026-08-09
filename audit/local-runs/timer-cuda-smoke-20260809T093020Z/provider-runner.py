from __future__ import annotations
import hashlib
import json
import os
import platform
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

def _deny_network(*args, **kwargs):
    raise RuntimeError('NETWORK_ACCESS_BLOCKED_BY_TIMER_CUDA_SMOKE')

socket.create_connection = _deny_network
socket.socket.connect = _deny_network

import torch
import transformers
from transformers import AutoModelForCausalLM

snap = Path(os.environ['SNAP']).resolve()
out_json = Path(os.environ['OUT_JSON'])
ready_file = Path(os.environ['READY_FILE'])
started_at = os.environ['STARTED_AT']
expected_gpu_uuid = os.environ['EXPECTED_GPU_UUID']

torch.manual_seed(1)
torch.cuda.manual_seed_all(1)
torch.set_grad_enabled(False)
torch.cuda.set_device(0)
torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats(0)

model = AutoModelForCausalLM.from_pretrained(
    str(snap),
    trust_remote_code=True,
    local_files_only=True,
    torch_dtype=torch.float32,
)
model.eval()
model.to('cuda:0')
torch.cuda.synchronize(0)
params = list(model.parameters())
buffers = list(model.buffers())
parameter_count = sum(p.numel() for p in params)
finite_parameters = all(bool(torch.isfinite(p).all().item()) for p in params)
finite_buffers = all(bool(torch.isfinite(b).all().item()) for b in buffers if b.is_floating_point())
model_device = str(params[0].device) if params else 'cuda:0'
if not model_device.startswith('cuda'):
    raise RuntimeError(f'model is not on CUDA: {model_device}')
x = torch.linspace(-1.0, 1.0, steps=96, dtype=torch.float32, device='cuda:0').reshape(1, 96)
if not str(x.device).startswith('cuda'):
    raise RuntimeError(f'input tensor is not on CUDA: {x.device}')
ready_file.write_text(json.dumps({'pid': os.getpid(), 'model_device': model_device, 'input_device': str(x.device)}) + '\n', encoding='utf-8')
time.sleep(3.0)
with torch.inference_mode():
    y = model.generate(x, max_new_tokens=1)
torch.cuda.synchronize(0)
if y.ndim != 2 or y.shape[0] != 1:
    raise RuntimeError(f'unexpected output shape: {tuple(y.shape)}')
if not str(y.device).startswith('cuda'):
    raise RuntimeError(f'output tensor is not on CUDA: {y.device}')
if not bool(torch.isfinite(y).all().item()):
    raise RuntimeError('non-finite CUDA smoke output')
raw = y.detach().cpu().contiguous().numpy().tobytes()
prediction_sha256 = hashlib.sha256(raw).hexdigest()
props = torch.cuda.get_device_properties(0)
payload = {
    'schema_version': 'timer-base-84m.offline-cuda-smoke.v2',
    'status': 'PASS',
    'source_head_sha': os.environ['SOURCE_HEAD'],
    'started_at_utc': started_at,
    'ended_at_utc': datetime.now(timezone.utc).isoformat(),
    'pid': os.getpid(),
    'python': sys.version.split()[0],
    'platform': platform.platform(),
    'torch': torch.__version__,
    'torch_cuda_build': torch.version.cuda,
    'transformers': transformers.__version__,
    'model_class': model.__class__.__name__,
    'parameter_count': parameter_count,
    'finite_parameters': finite_parameters,
    'finite_float_buffers': finite_buffers,
    'requested_device': 'cuda',
    'effective_device': model_device,
    'model_on_cuda': model_device.startswith('cuda'),
    'input_device': str(x.device),
    'output_device': str(y.device),
    'cpu_fallback': False,
    'input_shape': list(x.shape),
    'output_shape': list(y.shape),
    'prediction_sha256': prediction_sha256,
    'network_policy': 'HF/Transformers offline + local_files_only + Python socket deny guard',
    'snapshot_path': str(snap),
    'synthetic_input_only': True,
    'holdout_accessed': False,
    'prospective_accessed': False,
    'gpu_uuid_expected_from_nvidia_smi': expected_gpu_uuid,
    'cuda_device_name': props.name,
    'torch_peak_memory_allocated_bytes': int(torch.cuda.max_memory_allocated(0)),
    'torch_peak_memory_reserved_bytes': int(torch.cuda.max_memory_reserved(0)),
}
if not finite_parameters or not finite_buffers:
    raise RuntimeError('non-finite model parameter/buffer detected')
out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps(payload, sort_keys=True))
time.sleep(2.0)
