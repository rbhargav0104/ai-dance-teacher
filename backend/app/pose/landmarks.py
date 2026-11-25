"""MediaPipe Pose (BlazePose, 33 landmarks) topology: names, groups, skeleton, mirror map."""

from __future__ import annotations

NUM_LANDMARKS = 33

NAMES: tuple[str, ...] = (
    "nose",
    "left_eye_inner",
    "left_eye",
    "left_eye_outer",
    "right_eye_inner",
    "right_eye",
    "right_eye_outer",
    "left_ear",
    "right_ear",
    "mouth_left",
    "mouth_right",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_pinky",
    "right_pinky",
    "left_index",
    "right_index",
    "left_thumb",
    "right_thumb",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_foot_index",
    "right_foot_index",
)
assert len(NAMES) == NUM_LANDMARKS

IDX = {name: i for i, name in enumerate(NAMES)}

NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_HEEL, R_HEEL = 29, 30
L_FOOT, R_FOOT = 31, 32

CORE = (L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)
MAJOR = (
    L_SHOULDER,
    R_SHOULDER,
    L_ELBOW,
    R_ELBOW,
    L_WRIST,
    R_WRIST,
    L_HIP,
    R_HIP,
    L_KNEE,
    R_KNEE,
    L_ANKLE,
    R_ANKLE,
)
FEET = (L_ANKLE, R_ANKLE, L_HEEL, R_HEEL, L_FOOT, R_FOOT)

# Bones drawn by the skeleton viewer (pairs of landmark indices).
CONNECTIONS: tuple[tuple[int, int], ...] = (
    (11, 12),
    (11, 13),
    (13, 15),
    (15, 17),
    (15, 19),
    (15, 21),
    (17, 19),
    (12, 14),
    (14, 16),
    (16, 18),
    (16, 20),
    (16, 22),
    (18, 20),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (27, 29),
    (29, 31),
    (27, 31),
    (24, 26),
    (26, 28),
    (28, 30),
    (30, 32),
    (28, 32),
    (0, 2),
    (0, 5),
    (2, 7),
    (5, 8),
    (9, 10),
)


def _mirror_map() -> tuple[int, ...]:
    out = []
    for name in NAMES:
        if name.startswith("left_"):
            out.append(IDX["right_" + name[5:]])
        elif name.startswith("right_"):
            out.append(IDX["left_" + name[6:]])
        elif name == "mouth_left":
            out.append(IDX["mouth_right"])
        elif name == "mouth_right":
            out.append(IDX["mouth_left"])
        else:
            out.append(IDX[name])
    return tuple(out)


# MIRROR[i] = index of the anatomically opposite landmark (self for the nose).
MIRROR: tuple[int, ...] = _mirror_map()

# Joint angles: name -> (a, vertex, b). The angle is measured at `vertex`.
ANGLES: dict[str, tuple[int, int, int]] = {
    "left_elbow": (L_SHOULDER, L_ELBOW, L_WRIST),
    "right_elbow": (R_SHOULDER, R_ELBOW, R_WRIST),
    "left_shoulder": (L_HIP, L_SHOULDER, L_ELBOW),
    "right_shoulder": (R_HIP, R_SHOULDER, R_ELBOW),
    "left_hip": (L_SHOULDER, L_HIP, L_KNEE),
    "right_hip": (R_SHOULDER, R_HIP, R_KNEE),
    "left_knee": (L_HIP, L_KNEE, L_ANKLE),
    "right_knee": (R_HIP, R_KNEE, R_ANKLE),
    "left_ankle": (L_KNEE, L_ANKLE, L_FOOT),
    "right_ankle": (R_KNEE, R_ANKLE, R_FOOT),
}
