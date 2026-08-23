"""pytest 루트 설정: 프로젝트 루트를 import 경로에 추가해 `src.*` 임포트를 가능하게 한다."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
