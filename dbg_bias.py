import sys
sys.path.insert(0, ".")
import types
from datetime import datetime, timedelta

src = open("scifvg_main.py").read()
stub_src = '''
class _StubBase:
    def __init__(self, *a, **k):
        pass


class QCAlgorithm(_StubBase):
    pass


class FeeModel(_StubBase):
    pass


class OrderFee:
    def __init__(self, *a):
        pass


class CashAmount:
    def __init__(self, *a):
        pass


class _EnumNS:
    SUBMITTED = 101
    FILLED = 102
    CANCELED = 103
    CANCEL_PENDING = 104
    INVALID = 105


OrderStatus = _EnumNS
'''
mod = types.ModuleType("m")
mod.__dict__["timedelta"] = timedelta
mod.__dict__["types"] = types
exec(compile(stub_src, "<s>", "exec"), mod.__dict__)
exec(compile(src.replace("from AlgorithmImports import *", ""), "x", "exec"), mod.__dict__)

Alg = mod.SweepCisdIfvgAlgorithm
a = Alg.__new__(Alg)
a.fun = {}
a.cfg = {"sweep_min_ticks": 4}
a.tick = 0.25
a.bars5 = []
a.h4_pub = []
a.h4_bucket = None
a.swing_hi = []
a.swing_lo = []
a.bias = 0

base = datetime(2024, 1, 1)
levels = [100, 99, 98, 90, 91, 92, 91, 89,
          90, 91, 92, 97, 92, 91, 92, 93,
          95, 96, 97, 98, 99, 100, 101, 102]
for k, px in enumerate(levels):
    et = base + timedelta(hours=4 * k)
    bid = (et.year, et.month, et.day, et.hour // 4)
    if a.h4_bucket is not None and a.h4_bucket["id"] != bid:
        a._publish_h4(bid)
    if a.h4_bucket is None or a.h4_bucket["id"] != bid:
        a.h4_bucket = {"id": bid, "bars": [], "offset0": 0}
    for _ in range(8):
        a.h4_bucket["bars"].append({"open": px, "high": px, "low": px,
                                    "close": px, "et": et})
a._publish_h4((-1, -1, -1, -99))
print("published:", len(a.h4_pub))
print("swing_hi:", a.swing_hi)
print("swing_lo:", a.swing_lo)
print("bias:", a.bias)
