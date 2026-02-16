import os
import cv2
import numpy as np
from typing import Dict, Tuple, Optional

class SigilMatcher:
    def __init__(self, sigil_dir: str, ratio_test: float = 0.75, min_matches: int = 18):
        self.sigil_dir = sigil_dir
        self.ratio_test = ratio_test
        self.min_matches = min_matches

        self.orb = cv2.ORB_create(nfeatures=1500, scaleFactor=1.2, nlevels=8)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

        self.db: Dict[str, np.ndarray] = {}
        self._load_db()

    def _load_db(self) -> None:
        if not os.path.isdir(self.sigil_dir):
            raise RuntimeError(f"SIGIL_DIR not found: {self.sigil_dir}")

        for fn in sorted(os.listdir(self.sigil_dir)):
            if not fn.endswith(".png"):
                continue
            card_id = os.path.splitext(fn)[0]
            path = os.path.join(self.sigil_dir, fn)
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            kp, des = self.orb.detectAndCompute(img, None)
            if des is None or len(kp) < 10:
                continue
            self.db[card_id] = des

        if len(self.db) < 10:
            raise RuntimeError(f"Sigil DB too small ({len(self.db)}). Did you generate sigils?")

    def match(self, frame_bgr: np.ndarray) -> Tuple[Optional[str], float, int, dict]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3,3), 0)

        kp, des = self.orb.detectAndCompute(gray, None)
        if des is None or len(kp) < 10:
            return None, 0.0, 0, {"reason": "no_features"}

        best_id = None
        best_matches = 0
        best_score = 0.0

        for card_id, sig_des in self.db.items():
            matches = self.bf.knnMatch(sig_des, des, k=2)
            good = 0
            for m, n in matches:
                if m.distance < self.ratio_test * n.distance:
                    good += 1

            score = good / max(1, len(sig_des))
            if good > best_matches or (good == best_matches and score > best_score):
                best_id = card_id
                best_matches = good
                best_score = score

        ok = best_matches >= self.min_matches
        conf = float(min(1.0, best_score * 3.0))
        debug = {
            "best_id": best_id,
            "best_matches": best_matches,
            "best_score": best_score,
            "min_matches": self.min_matches,
            "ratio_test": self.ratio_test
        }
        if not ok:
            return None, conf, best_matches, debug
        return best_id, conf, best_matches, debug
