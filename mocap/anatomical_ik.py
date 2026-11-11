"""Source-preserving, fixed anatomical-axis correction for two leg chains.

Only the corrective knee increment is constrained here: existing inferred
SMPL-X rotations are never rewritten into a different neutral skeleton.
Export fitting separately enforces its complete signed one-axis hinges.
"""
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.ndimage import gaussian_filter1d
from .mixamo_rig import align

_POLE_SMOOTH_SIGMA = 1.0
# Rotating the femur to restore the knee swing plane is the same degree of
# freedom the eye reads as a thigh roll. Keep only a fraction of it: the full
# correction removes the knee flip but makes the thigh snap on adjacent frames.
_POLE_STRENGTH = .25


def reach_lengths(rest,world):
    """Maximum physical reach with the source's non-hinge components fixed."""
    lengths=[]
    for hip,knee,ankle in ((1,4,7),(2,5,8)):
        upper=rest[knee]-rest[hip];lower=rest[ankle]-rest[knee]
        axis=align([0,-1,0],upper)@np.array([1.,0,0])
        local=world[:,hip].swapaxes(-1,-2)@world[:,knee]
        v=np.einsum('tij,j->ti',local,lower)
        perpendicular=v-(v@axis)[:,None]*axis
        radius=np.hypot(perpendicular@upper,np.cross(axis,v)@upper)
        constant=(upper@axis)*(v@axis)
        lengths.append(np.sqrt(np.maximum(0,np.dot(upper,upper)+np.dot(lower,lower)+2*(constant+radius))))
    return np.stack(lengths,axis=1)


def minimum_reach_lengths(rest,world):
    """Physical minimum reach at the native solver's 160 degree flex limit."""
    lengths=[]
    for hip,knee,ankle in ((1,4,7),(2,5,8)):
        upper=rest[knee]-rest[hip];lower=rest[ankle]-rest[knee]
        axis=align([0,-1,0],upper)@np.array([1.,0,0])
        local=world[:,hip].swapaxes(-1,-2)@world[:,knee]
        v=np.einsum('tij,j->ti',local,lower)
        perpendicular=v-(v@axis)[:,None]*axis
        radius=np.hypot(perpendicular@upper,np.cross(axis,v)@upper)
        constant=(upper@axis)*(v@axis)
        lengths.append(np.sqrt(np.maximum(0,np.dot(upper,upper)+np.dot(lower,lower)+
                                         2*(constant+radius*np.cos(np.deg2rad(160.))))))
    return np.stack(lengths,axis=1)


def _rebuild_knees(ids, reference, upper, lower, axis, original_knee, source_world_hip,
                   origin, delta, phase, flex, hip, knee, ankle):
    """Restore the knee swing plane and bend on legs straightened by balance.

    balance rotates the body about the sole with the ankles pinned, which
    stretches the hip-ankle line and can flatten a leg to its reach limit.
    There align(end_vector, delta) has no stable basis for the knee swing
    plane and the pole flips between frames. The source (pre-balance) pole and
    a fraction of the source bend are restored; both remain inside the
    anatomical hinge -- a bend about axis plus a twist about the hip-ankle
    line -- so the ankle, the global orientations and every balance metric
    stay untouched. balance_pose rolls the repair back on any frame where it
    would itself introduce a new jump.
    """
    m = len(ids)
    rd = reference[ids, ankle] - reference[ids, hip]
    rax = rd / np.maximum(np.linalg.norm(rd, axis=1, keepdims=True), 1e-12)
    rv = reference[ids, knee] - reference[ids, hip]
    rperp = rv - (rv * rax).sum(1, keepdims=True) * rax
    bow_src = np.linalg.norm(rperp, axis=1)
    pole_src = rperp / np.maximum(bow_src[:, None], 1e-12)
    ax = delta / np.maximum(np.linalg.norm(delta, axis=1, keepdims=True), 1e-12)
    pg = pole_src - (pole_src * ax).sum(1, keepdims=True) * ax
    pgn = np.linalg.norm(pg, axis=1, keepdims=True)
    pg = np.where(pgn > 1e-9, pg / np.maximum(pgn, 1e-12), 0.)
    flex_goal = np.maximum(flex, .40 * bow_src / max(np.linalg.norm(upper), 1e-12))
    ev_raw = upper + np.einsum('tij,j->ti',
                               Rotation.from_rotvec((phase + flex)[:, None] * axis).as_matrix() @ original_knee,
                               lower)
    hw_raw = source_world_hip.copy()
    for t in range(m):
        hw_raw[t] = align(hw_raw[t] @ ev_raw[t], delta[t]) @ hw_raw[t]
    u_raw = np.einsum('tij,j->ti', hw_raw, upper)
    bow = np.linalg.norm(u_raw - (u_raw * ax).sum(1, keepdims=True) * ax, axis=1)
    gate = np.clip((bow / np.maximum(bow_src, 1e-12) - .90) / .25, 0., 1.)

    # The kink guard lives in balance_pose, where the full take is available:
    # the contact mask has gaps, so a guard over just these ids would miss
    # jumps on frames neighbouring a repaired one.
    corr = phase + flex_goal
    bend = Rotation.from_rotvec(corr[:, None] * axis).as_matrix()
    knee_local = bend @ original_knee
    ev = upper + np.einsum('tij,j->ti', knee_local, lower)
    hw = source_world_hip.copy()
    for t in range(m):
        hw[t] = align(hw[t] @ ev[t], delta[t]) @ hw[t]
    psi = np.zeros(m)
    for t in range(m):
        if not np.isfinite(pg[t]).all() or np.linalg.norm(pg[t]) < 1e-9:
            continue
        u = hw[t] @ upper
        bv = u - (u @ ax[t]) * ax[t]
        bn = np.linalg.norm(bv)
        if bn < 1e-9:
            continue
        ang = np.arctan2(np.cross(pg[t], bv / bn) @ ax[t], pg[t] @ (bv / bn))
        psi[t] = -(1. - gate[t]) * ang
    # A raw pole correction jumps between frames when the leg is fully
    # stretched; applied directly it becomes a one-frame femur roll. Spread
    # the correction over neighbouring frames instead (non-causal: solve_legs
    # already works on the whole take). Contact gaps simply fade it in/out.
    full = np.zeros(len(reference))
    lo, hi = ids[0], ids[-1]
    full[lo:hi + 1] = np.interp(np.arange(lo, hi + 1), ids, psi)
    psi = _POLE_STRENGTH * gaussian_filter1d(full, _POLE_SMOOTH_SIGMA, mode='nearest')[ids]
    for t in range(m):
        hw[t] = Rotation.from_rotvec(ax[t] * psi[t]).as_matrix() @ hw[t]
    return flex_goal, corr, bend, knee_local, hw


def solve_legs(rest, source_positions, source_world, roots, targets, active, reference=None):
    from .correction import PARENTS
    n=len(roots);local=source_world.copy()
    for j,p in enumerate(PARENTS):
        if p>=0:local[:,j]=source_world[:,p].swapaxes(-1,-2)@source_world[:,j]
    original=local.copy()
    root_shift=roots-source_positions[:,0]
    max_delta=0.;max_off_axis=0.;max_flex=0.
    for foot,(hip,knee,ankle) in enumerate(((1,4,7),(2,5,8))):
        ids=np.flatnonzero(active[:,foot])
        if not len(ids):continue
        upper=rest[knee]-rest[hip];lower=rest[ankle]-rest[knee]
        # Same canonical->source neutral calibration as the exported femur.
        calibration=align([0,-1,0],upper)
        axis=calibration@np.array([1.,0,0])
        v=np.einsum('tij,j->ti',original[ids,knee],lower)
        dot=v@axis
        perpendicular=v-dot[:,None]*axis
        a=perpendicular@upper;b=np.cross(axis,v)@upper
        constant=(upper@axis)*dot
        radius=np.hypot(a,b)
        origin=source_positions[ids,hip]+root_shift[ids]
        delta=targets[ids,foot]-origin
        distance=np.linalg.norm(delta,axis=1)
        desired=(distance**2-np.dot(upper,upper)-np.dot(lower,lower))*.5-constant
        # The positive branch flexes around the calibrated anatomical axis.
        # Unlike cross(hip-knee, knee-ankle), rest curvature cannot change it.
        phase=np.arctan2(b,a)
        flex=np.minimum(np.arccos(np.clip(desired/np.maximum(radius,1e-12),-1,1)),np.deg2rad(160))
        correction=phase+flex
        bend=Rotation.from_rotvec(correction[:,None]*axis).as_matrix()
        knee_local=bend@original[ids,knee]
        end_vector=upper+np.einsum('tij,j->ti',knee_local,lower)
        hip_world=source_world[ids,hip].copy()
        for t,i in enumerate(ids):
            hip_world[t]=align(hip_world[t]@end_vector[t],delta[t])@hip_world[t]
        if reference is not None:
            flex,correction,bend,knee_local,hip_world=_rebuild_knees(
                ids,reference,upper,lower,axis,original[ids,knee],source_world[ids,hip],
                origin,delta,phase,flex,hip,knee,ankle)
        local[ids,hip]=source_world[ids,PARENTS[hip]].swapaxes(-1,-2)@hip_world
        local[ids,knee]=knee_local
        # Ankle rotation controls the foot only, never incoming shin roll.
        local[ids,ankle]=(hip_world@knee_local).swapaxes(-1,-2)@source_world[ids,ankle]
        rv=Rotation.from_matrix(bend).as_rotvec()
        off=rv-(rv@axis)[:,None]*axis
        max_off_axis=max(max_off_axis,float(np.linalg.norm(off,axis=1).max()))
        max_delta=max(max_delta,float(np.abs(correction).max()))
        max_flex=max(max_flex,float(flex.max()))
    if max_off_axis>1e-7 or not np.isfinite(local).all():
        raise ValueError('Anatomical knee correction failed its axis validation')
    return local,dict(max_added_knee_off_axis_deg=float(np.rad2deg(max_off_axis)),
                      max_added_knee_rotation_deg=float(np.rad2deg(max_delta)),
                      max_corrected_knee_flex_deg=float(np.rad2deg(max_flex)))
