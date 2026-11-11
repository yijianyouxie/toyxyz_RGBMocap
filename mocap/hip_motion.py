"""Export the pelvis motion the video shows, not the rolled-out world root.

ExMR integrates the world root from a separately predicted root velocity and then only
re-anchors it to the camera-frame root where the deviation exceeds 0.25 m (2 s Gaussian
reference). A dance that stays in place therefore keeps the integration's own slow sway and
its own vertical rhythm: the exported root can differ from the video by a quarter of a metre
horizontally and be out of phase vertically.

```match_video``` replaces the exported root with the camera-frame root, which is the one
fitted to the frames, and then optionally scales the remaining excursion about the take
median. Poses, joint rotations and the world frame are untouched: only the root translation
changes, so the caller has to run it before the BVH is written.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

from .mixamo_rig import align

# The camera-frame root is a per-frame image fit. The image pins the height and the horizontal
# placement, so the pose can absorb a sway: that axis arrives with the fit's ripple (about twice
# the keypoints' own fast sway on the Valentine take). One frame of smoothing keeps the sway.
HORIZONTAL_FRAMES = 1.0
# The depth is the axis the fit is least sure about, and a vertical bounce is ambiguous with
# moving toward the camera: the Valentine take swings 0.20 m of depth inside 0.6 s of a hip lift
# that really lifts 0.10 m. That reads as the character lunging at the camera and buries the bob.
# Keep only the slow part of the depth; a real step to or from the camera survives.
DEPTH_SECONDS = 0.5
# One excursion gain below or above these is a mistake, not a taste.
GAIN_LIMITS = (0.2, 3.0)
# Frames per forward pass; longer takes are processed in blocks to bound the mesh memory.
CHUNK = 256

# The knee bends about the body's left-right axis (sagittal flexion). ExMR's
# legs are ~98.5% straight, so its own per-frame knee pole (phase) is noise that
# flips the bend toward/away from the camera 18-21 times a take. Dropping the
# phase and fixing the flex sign keeps the knee bowed toward the camera (world
# -Z for a head-on take), which is the only bend visible in the 2D.
BEND_LIMITS = (0.0, 1.0)
# Foot reference: the take's lowest sole, low-passed, is the floor. The foot
# rises only 3.4 cm against a 12.9 cm pelvis excursion, so treat it as planted.
SOLE_SECONDS = 1.0
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
    """The camera-frame root with its ripple removed: horizontal lightly, depth heavily."""
    horizontal = _gaussian(camera[:, :1], HORIZONTAL_FRAMES)[:, 0]
    depth = _gaussian(camera[:, 2:3], DEPTH_SECONDS * fps)[:, 0]
    return np.stack([horizontal, camera[:, 1], depth], axis=1)


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


def _plant_legs_toward_camera(rest, positions, world, targets):
    """Two-bone IK: ankles to targets, knees bowed toward the camera (fixed +flex).

    Returns local rotation matrices (n,22,3,3), the body_pose in matrix form.
    """
    n = len(positions)
    local = world.copy()
    for j, p in enumerate(_LEG_PARENTS):
        if p >= 0:
            local[:, j] = world[:, p].swapaxes(-1, -2) @ world[:, j]
    original = local.copy()
    for foot, (hip, knee, ankle) in enumerate(((1, 4, 7), (2, 5, 8))):
        upper = rest[knee] - rest[hip]; lower = rest[ankle] - rest[knee]
        calibration = align([0, -1, 0], upper)
        axis = calibration @ np.array([1., 0, 0])
        v = np.einsum('tij,j->ti', original[:, knee], lower)
        dot = v @ axis; perpendicular = v - dot[:, None] * axis
        a = perpendicular @ upper; b = np.cross(axis, v) @ upper
        constant = (upper @ axis) * dot
        radius = np.hypot(a, b)
        delta = targets[:, foot] - positions[:, hip]
        distance = np.linalg.norm(delta, axis=1)
        desired = (distance ** 2 - upper @ upper - lower @ lower) * .5 - constant
        flex = np.minimum(np.arccos(np.clip(desired / np.maximum(radius, 1e-12), -1, 1)), np.deg2rad(160))
        correction = flex  # fixed positive: knee bows toward the camera (world -Z), no phase flip
        bend = Rotation.from_rotvec(correction[:, None] * axis).as_matrix()
        knee_local = bend @ original[:, knee]
        end_vector = upper + np.einsum('tij,j->ti', knee_local, lower)
        hip_world = world[:, hip].copy()
        for t in range(n):
            hip_world[t] = align(hip_world[t] @ end_vector[t], delta[t]) @ hip_world[t]
        local[:, hip] = world[:, _LEG_PARENTS[hip]].swapaxes(-1, -2) @ hip_world
        local[:, knee] = knee_local
        local[:, ankle] = (hip_world @ knee_local).swapaxes(-1, -2) @ world[:, ankle]
    return local


def absorb_vertical(record, body, bend=1.0, fps=30.0):
    """Plant the feet and absorb the pelvis height into knee flexion.

    bend=0 returns the input unchanged (the old whole-body bob); bend=1 plants
    both feet and bows the knees toward the camera. Returns (transl, body_pose).
    """
    if not BEND_LIMITS[0] <= bend <= BEND_LIMITS[1]:
        raise ValueError(f"Hip knee bend must be within {BEND_LIMITS[0]}-{BEND_LIMITS[1]}")
    g = record["smpl_params_global"]
    transl = g["transl"].numpy().astype(np.float64)
    body_pose = g["body_pose"].numpy().astype(np.float64).reshape(-1, 21, 3)
    if bend == 0.0:
        return transl, body_pose.reshape(-1, 63)
    n = len(transl)
    rest = _rest_joints(body, g["betas"][0].numpy())
    mean = body.pose_mean.numpy().reshape(55, 3)
    abs_aa = np.zeros((n, 22, 3))
    abs_aa[:, 0] = g["global_orient"].numpy()
    abs_aa[:, 1:22] = body_pose + mean[1:22]
    positions, world = _forward_aa(rest, transl, abs_aa)
    # floor: lowest sole low-passed; foot rises 3.4 cm vs 12.9 cm pelvis, treated planted
    foot_low = np.minimum(positions[:, 10, 1], positions[:, 11, 1])
    ground = _gaussian(foot_low[:, None], SOLE_SECONDS * fps)[:, 0]
    targets = np.empty((n, 2, 3))
    for foot, (ankle_i, foot_i) in enumerate(((7, 10), (8, 11))):
        offset = positions[:, ankle_i, 1] - positions[:, foot_i, 1]
        targets[:, foot] = positions[:, ankle_i].copy()
        planted = ground + offset
        targets[:, foot, 1] = positions[:, ankle_i, 1] + bend * (planted - positions[:, ankle_i, 1])
    local = _plant_legs_toward_camera(rest, positions, world, targets)
    new_abs = Rotation.from_matrix(local.reshape(-1, 3, 3)).as_rotvec().reshape(n, 22, 3)
    new_body_pose = (new_abs[:, 1:22] - mean[1:22]).reshape(n, 63)
    return transl, new_body_pose


def match_video(record, body_path, sway=1.0, bob=1.0, fps=30.0):
    """World translation whose root follows the video, with the excursion gains applied.

    `record` is the ExMR record that is about to be saved as hmr4d_results.pt, so it holds
    both spaces. Every downstream consumer (correction, BVH, npz, preview) reads this one
    translation and therefore agrees.
    """
    for key, limit in (("sway", sway), ("bob", bob)):
        if not np.isfinite(limit) or not GAIN_LIMITS[0] <= limit <= GAIN_LIMITS[1]:
            raise ValueError(f"Hip {key} gain must be within {GAIN_LIMITS[0]}-{GAIN_LIMITS[1]}")
    world = record["smpl_params_global"]
    camera = record["smpl_params_incam"]
    body = _body(body_path, CHUNK)
    world_root = _pelvis(body, world)
    camera_root = _pelvis(body, camera)
    followed = follow_camera_root(world["transl"], world_root, camera_root,
                                  world["global_orient"], camera["global_orient"], fps)
    return scale_excursion(followed, sway, bob)
