"""Export the pelvis motion the video shows, not the rolled-out world root.

ExMR integrates the world root from a separately predicted root velocity and then only
re-anchors it to the camera-frame root where the deviation exceeds 0.25 m (2 s Gaussian
reference). A dance that stays in place therefore keeps the integration's own slow sway and
its own vertical rhythm: the exported root can differ from the video by a quarter of a metre
horizontally and be out of phase vertically.

```match_video``` replaces the exported root with the camera-frame root, which is the one
fitted to the frames, scales the remaining excursion about the take median, and then refits
the legs (UpLeg/Leg) from the video 2D keypoints so the knees squat-and-straighten in the
sagittal plane instead of bowing toward the camera. Only the root translation and the leg
rotations change, so the caller has to run it before the BVH is written.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

from .mixamo_rig import align

# The camera-frame root is a per-frame image fit. The image pins the height and the horizontal
# placement, so the pose can absorb a sway: that axis arrives with the fit's ripple (about twice
# the keypoints' own fast sway on the Valentine take). Two frames of smoothing keep the sway
# without letting the ripple read as a side-to-side jitter.
HORIZONTAL_FRAMES = 2.0
# The height is pinned hard in the image, but the per-frame fit still carries a
# frame-to-frame ripple that reads as a vertical bounce after the root follows it;
# two frames of Gaussian sigma remove it without cutting the ~1.5 s hip rhythm.
VERTICAL_FRAMES = 2.0
# The depth is the axis the fit is least sure about, and a vertical bounce is ambiguous with
# moving toward the camera: the Valentine take swings 0.20 m of depth inside 0.6 s of a hip lift
# that really lifts 0.10 m. That reads as the character lunging at the camera and buries the bob.
# Keep only the slow part of the depth; a real step to or from the camera survives.
DEPTH_SECONDS = 0.5
# One excursion gain below or above these is a mistake, not a taste.
GAIN_LIMITS = (0.2, 3.0)
# Frames per forward pass; longer takes are processed in blocks to bound the mesh memory.
CHUNK = 256

# The 2D-driven leg refit mixes the optimized sagittal knee bend toward the
# ExMR original: 0 keeps ExMR's legs, 1 replaces the UpLeg/Leg rotations with
# the 2D fit. The range is shared with exmr_options through BEND_LIMITS.
BEND_LIMITS = (0.0, 1.0)
# COCO knee keypoints sit on the patella's lower front while SMPL knee joints
# sit on the femur-tibia centre; the thigh angular distance is systematically
# ~7.8% longer (a constant offset, not motion-coupled). Shorten the video knee
# along the hip->knee direction before the 2D fit.
KNEE_CORR = 1.0 / 1.078
# Residual scales for refit_legs (the sagittal knee refit).
REFIT_V_SIGMA = 8.0      # thigh projection v alignment (px)
REFIT_LEN_SIGMA = 0.06   # soft shin-length prior (relative)
REFIT_FLEX_SIGMA = 1.0   # flexion-angle prior (rad)
# The sagittal flexion must not push the knee behind the hip (a backward bend);
# a positive z excess is penalised hard, so the knee stays forward of the hip.
REFIT_FORWARD_SIGMA = 0.05
# 2D keypoint noise makes the per-frame flexion jitter; low-pass the fitted
# angles along time. This is frames of Gaussian sigma, so the ~1.5 s squat rhythm survives.
REFIT_SMOOTH_FRAMES = 2.0
# SMPL-X 22-joint parent list, copied from correction.PARENTS to avoid importing
# correction (which pulls the KimodoMotionCorrection .pyd chain into the exmr worker).
_LEG_PARENTS = [-1, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 12, 13, 14, 16, 17, 18, 19]


def _gaussian(values, sigma):
    """Gaussian smoothing along the frame axis with replicate padding."""
    if sigma <= 0:
        return values
    radius = int(4 * sigma + 0.5)
    kernel = np.exp(-0.5 / sigma ** 2 * np.arange(-radius, radius + 1) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(values, ((radius, radius), (0, 0)), mode="edge")
    return np.stack(
        [np.convolve(padded[:, column], kernel, mode="valid") for column in range(values.shape[1])],
        axis=1,
    )


def _camera_path(camera, fps):
    """The camera-frame root with its ripple removed: horizontal and vertical lightly, depth heavily."""
    horizontal = _gaussian(camera[:, :1], HORIZONTAL_FRAMES)[:, 0]
    vertical = _gaussian(camera[:, 1:2], VERTICAL_FRAMES)[:, 0]
    depth = _gaussian(camera[:, 2:3], DEPTH_SECONDS * fps)[:, 0]
    return np.stack([horizontal, vertical, depth], axis=1)


def _matrix(axis_angle):
    from scipy.spatial.transform import Rotation
    return Rotation.from_rotvec(np.asarray(axis_angle, np.float64)).as_matrix()


def _body(body_path, chunk):
    import smplx
    return smplx.SMPLX(str(body_path), flat_hand_mean=False, use_pca=False, batch_size=chunk).eval()


def _pelvis(model, params, chunk=CHUNK):
    """SMPL-X pelvis joint per frame through one already loaded body model."""
    import torch

    count = len(params["transl"])
    out = []
    with torch.no_grad():
        for start in range(0, count, chunk):
            block = {key: np.asarray(value[start:start + chunk], np.float32) for key, value in params.items()
                     if key in ("global_orient", "body_pose", "betas", "transl")}
            size = len(block["transl"])
            if size < chunk:  # smplx keeps its batch size; repeat the last frame and slice it off
                block = {key: np.concatenate([value, np.repeat(value[-1:], chunk - size, axis=0)])
                         for key, value in block.items()}
            joints = model(
                global_orient=torch.from_numpy(block["global_orient"]).view(chunk, 1, 3),
                body_pose=torch.from_numpy(block["body_pose"]).view(chunk, 21, 3),
                betas=torch.from_numpy(block["betas"]),
                transl=torch.from_numpy(block["transl"]),
                left_hand_pose=torch.zeros(chunk, 45),
                right_hand_pose=torch.zeros(chunk, 45),
            ).joints[:, 0].numpy()
            out.append(joints[:size])
    return np.concatenate(out).astype(np.float64)


def pelvis_joint(body_path, params, chunk=CHUNK):
    """SMPL-X pelvis joint per frame, the joint ExMR's own root correction works on."""
    return _pelvis(_body(body_path, chunk), params, chunk)


def follow_camera_root(transl, world_root, camera_root, world_orient, camera_orient, fps=30.0):
    """Shift the root translation so the world root reproduces the camera-frame root.

    `world_root` and `camera_root` are the pelvis joint in the world and in the camera frame.
    Moving the translation by the per-frame difference moves the pelvis with it, so the body
    keeps its pose and its orientation and only its placement follows the video.

    The ripple of the per-frame fit is removed by `_camera_path`: see the constants above.
    """
    rotation = _matrix(world_orient[0]) @ _matrix(camera_orient[0]).T
    translation = np.asarray(transl, np.float64)
    camera = _camera_path(np.asarray(camera_root, np.float64), fps)
    target = (camera - camera[0]) @ rotation.T + np.asarray(world_root, np.float64)[0]
    return translation + (target - np.asarray(world_root, np.float64))


def scale_excursion(transl, sway=1.0, bob=1.0):
    """Scale the excursion about the take median: the horizontal pair by sway, height by bob.

    The median keeps the take where it was, so the character does not step off its mark when
    the gain moves. A take that travels across the floor keeps that travel, scaled too: the
    gain is an amplitude on the whole path, which is what a dance in place needs.
    """
    gain = np.array([float(sway), float(bob), float(sway)], np.float64)
    center = np.median(np.asarray(transl, np.float64), axis=0)
    return center + (np.asarray(transl, np.float64) - center) * gain


def _bob_gain(camera_root, keypoints, K, fps=30.0):
    """Vertical root gain that restores the video's pelvis height excursion.

    The camera-frame pelvis projection keeps the video's phase but the monocular
    fit compresses its height; the video/projection v peak-to-peak ratio is the
    missing gain (about 1.16 on the Valentine take). The projection is measured
    on the same smoothed path the root follows, so the gain is auto-calibrated,
    not hand-tuned; a flat take (no excursion) leaves the root untouched.
    """
    keypoints = keypoints.detach().cpu().numpy() if hasattr(keypoints, "detach") else np.asarray(keypoints)
    keypoints = np.asarray(keypoints, np.float64)
    K = K.detach().cpu().numpy() if hasattr(K, "detach") else np.asarray(K)
    K = np.asarray(K, np.float64)
    if K.ndim == 3:
        K = K[0]
    fy, cy = K[1, 1], K[1, 2]
    camera = _camera_path(np.asarray(camera_root, np.float64), fps)
    projection = fy * camera[:, 1] / camera[:, 2] + cy
    pelvis_v = (keypoints[:, 11, 1] + keypoints[:, 12, 1]) / 2
    span = float(np.ptp(projection))
    if span < 1e-3:
        return 1.0
    return float(np.clip(np.ptp(pelvis_v) / span, GAIN_LIMITS[0], GAIN_LIMITS[1]))


def _rest_joints(body, betas):
    """22-joint shape-dependent rest, same as correction.SoleGeometry."""
    shaped = body.v_template.numpy() + np.einsum('vci,i->vc', body.shapedirs.numpy(), betas)
    return (body.J_regressor.numpy() @ shaped)[:22]


def _forward_aa(rest, root, abs_aa):
    """Absolute axis-angle local rotations (pose_mean already added) -> (positions, world)."""
    local = Rotation.from_rotvec(abs_aa.reshape(-1, 3)).as_matrix().reshape(len(root), 22, 3, 3)
    rotations = local.copy()
    positions = np.empty((len(root), 22, 3)); positions[:, 0] = root
    for j in range(1, 22):
        p = _LEG_PARENTS[j]
        positions[:, j] = positions[:, p] + np.einsum('tij,j->ti', rotations[:, p], rest[j] - rest[p])
        rotations[:, j] = rotations[:, p] @ local[:, j]
    return positions, rotations


def refit_legs(record, body, keypoints, K, fps=30.0, drive=1.0):
    """Refit the legs from the video 2D keypoints, replacing ExMR's camera-bowed
    knees with a sagittal flexion that follows the 2D.

    ExMR keeps the legs nearly straight vertically and explains the hip bob as a
    knee bend toward the camera. The 2D knee keypoints still carry the real
    squat-then-straighten rhythm, so each leg is refit per frame by rotating the
    knee about the body's left-right axis: the thigh projection follows the video
    (corrected for the COCO-knee/SMPL-knee definition offset) under a soft shin-
    length and flexion prior. The ankle stays put, so the feet keep their spacing.

    drive blends the fitted knees toward ExMR: 0 returns the input body_pose, 1
    replaces the UpLeg/Leg rotations entirely. Returns body_pose (n, 63).
    """
    if not BEND_LIMITS[0] <= drive <= BEND_LIMITS[1]:
        raise ValueError(f"Hip knee drive must be within {BEND_LIMITS[0]}-{BEND_LIMITS[1]}")
    from scipy.optimize import least_squares

    g = record["smpl_params_global"]
    incam = record["smpl_params_incam"]
    body_pose = g["body_pose"].numpy().astype(np.float64).reshape(-1, 21, 3)
    if drive == 0.0:
        return body_pose.reshape(-1, 63)
    n = len(body_pose)
    keypoints = keypoints.detach().cpu().numpy() if hasattr(keypoints, "detach") else np.asarray(keypoints)
    keypoints = np.asarray(keypoints, np.float64)
    K = K.detach().cpu().numpy() if hasattr(K, "detach") else np.asarray(K)
    K = np.asarray(K, np.float64)
    if K.ndim == 2:
        K = np.broadcast_to(K, (n, 3, 3))
    fx, fy = K[:, 0, 0], K[:, 1, 1]
    cx, cy = K[:, 0, 2], K[:, 1, 2]
    rest = _rest_joints(body, incam["betas"][0].numpy())
    mean = body.pose_mean.numpy().reshape(55, 3)
    abs_aa = np.zeros((n, 22, 3))
    abs_aa[:, 0] = incam["global_orient"].numpy()
    abs_aa[:, 1:22] = incam["body_pose"].numpy().reshape(-1, 21, 3) + mean[1:22]
    positions, joint_world = _forward_aa(rest, incam["transl"].numpy().astype(np.float64), abs_aa)
    # (hip, knee, ankle, COCO hip, COCO knee, COCO ankle, shin length)
    legs = (
        (1, 4, 7, 11, 13, 15, np.linalg.norm(rest[7] - rest[4])),
        (2, 5, 8, 12, 14, 16, np.linalg.norm(rest[8] - rest[5])),
    )
    flex = np.zeros((n, 2))
    for t in range(n):
        for li, (hip, knee, ankle, ch, ck, ca, shin_len) in enumerate(legs):
            H = positions[t, hip]; Kex = positions[t, knee]; A = positions[t, ankle]
            vector = Kex - H
            vH = fy[t] * H[1] / H[2] + cy[t]
            target_v = (keypoints[t, ck, 1] - keypoints[t, ch, 1]) * KNEE_CORR

            def residual(x, vector=vector, H=H, A=A, vH=vH, target_v=target_v, fyt=float(fy[t]), cyt=float(cy[t])):
                theta = x[0]
                cos, sin = np.cos(theta), np.sin(theta)
                rotated = np.array([vector[0], cos * vector[1] - sin * vector[2], sin * vector[1] + cos * vector[2]])
                knee_v = H + rotated
                vK = fyt * knee_v[1] / knee_v[2] + cyt
                return np.array([
                    (vK - vH - target_v) / REFIT_V_SIGMA,
                    (np.linalg.norm(A - knee_v) - shin_len) / (REFIT_LEN_SIGMA * shin_len),
                    theta / REFIT_FLEX_SIGMA,
                    max(0.0, knee_v[2] - H[2]) / REFIT_FORWARD_SIGMA,
                ])
            # Sagittal flexion must not push the knee behind the hip; the upper
            # bound is the angle that brings the knee level with the hip (or zero
            # if ExMR already placed it behind, so we never bend it further back).
            theta_max = max(0.0, float(np.arctan2(-vector[2], vector[1])))
            solution = least_squares(residual, np.zeros(1), method="trf",
                                      bounds=([-1.2], [theta_max]))
            flex[t, li] = solution.x[0] * drive
    # The per-frame fit follows the keypoint noise frame by frame; low-pass the
    # flexion along time so the legs do not jitter (see REFIT_SMOOTH_FRAMES).
    flex = _gaussian(flex, REFIT_SMOOTH_FRAMES)
    new_knee = np.zeros((n, 2, 3))
    for t in range(n):
        for li, (hip, knee, ankle, ch, ck, ca, shin_len) in enumerate(legs):
            H = positions[t, hip]; Kex = positions[t, knee]
            vector = Kex - H
            theta = flex[t, li]
            cos, sin = np.cos(theta), np.sin(theta)
            rotated = np.array([vector[0], cos * vector[1] - sin * vector[2], sin * vector[1] + cos * vector[2]])
            new_knee[t, li] = H + rotated
    # Inverse-kinematics the UpLeg/Leg rotations; the ankles keep their world rotation.
    local = joint_world.copy()
    for j, p in enumerate(_LEG_PARENTS):
        if p >= 0:
            local[:, j] = joint_world[:, p].swapaxes(-1, -2) @ joint_world[:, j]
    for li, (hip, knee, ankle) in enumerate(((1, 4, 7), (2, 5, 8))):
        upper = rest[knee] - rest[hip]; lower = rest[ankle] - rest[knee]
        for t in range(n):
            hip_world = align(joint_world[t, hip] @ upper, new_knee[t, li] - positions[t, hip]) @ joint_world[t, hip]
            knee_local = align(lower, hip_world.T @ (positions[t, ankle] - new_knee[t, li]))
            local[t, hip] = joint_world[t, _LEG_PARENTS[hip]].swapaxes(-1, -2) @ hip_world
            local[t, knee] = knee_local
            local[t, ankle] = (hip_world @ knee_local).swapaxes(-1, -2) @ joint_world[t, ankle]
    new_abs = Rotation.from_matrix(local.reshape(-1, 3, 3)).as_rotvec().reshape(n, 22, 3)
    return (new_abs[:, 1:22] - mean[1:22]).reshape(n, 63)


def match_video(record, body_path, sway=1.0, bend=1.0, fps=30.0, keypoints=None, K=None):
    """(transl, body_pose) whose root follows the video and whose legs are refit
    from the video 2D keypoints. sway scales the horizontal excursion; the vertical
    excursion is auto-calibrated to the video (6.1); bend is the knee drive (0 keeps
    ExMR's legs, 1 replaces them with the 2D refit).
    """
    if not GAIN_LIMITS[0] <= sway <= GAIN_LIMITS[1]:
        raise ValueError(f"Hip sway gain must be within {GAIN_LIMITS[0]}-{GAIN_LIMITS[1]}")
    world = record["smpl_params_global"]
    camera = record["smpl_params_incam"]
    body = _body(body_path, CHUNK)
    world_root = _pelvis(body, world)
    camera_root = _pelvis(body, camera)
    followed = follow_camera_root(world["transl"], world_root, camera_root,
                                  world["global_orient"], camera["global_orient"], fps)
    # 6.1: restore the compressed vertical excursion with the auto-calibrated gain.
    bob = _bob_gain(camera_root, keypoints, K, fps) if keypoints is not None and K is not None else 1.0
    followed = scale_excursion(followed, sway, bob)
    # apply the 2D leg refit on the record that will be saved
    import torch
    record_work = dict(record)
    record_work["smpl_params_global"] = dict(world)
    record_work["smpl_params_global"]["transl"] = torch.from_numpy(followed).to(world["transl"].dtype)
    if keypoints is None or K is None:
        body_pose = world["body_pose"].numpy().astype(np.float64)
    else:
        body_pose = refit_legs(record_work, body, keypoints, K, fps, bend)
    return followed, body_pose
