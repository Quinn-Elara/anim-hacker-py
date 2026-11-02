"""Blender helper for Anim Hacker: turns a point in Blender into a constraint offset.

An animation constraint's sourceOffset / targetOffset is a point given relative to a collision
volume (L_HAND, HEAD, ...), measured in units of that volume's size. This script works that
number out for a point you place in the scene.

How to use it
  1. Open your Second Life rig. It needs the standard joint bones (mPelvis, mTorso, mHead,
     mWristLeft, ...), as Avastar and the Linden Lab Blender rigs have.
  2. Show the rig in its rest pose: Armature data > Skeleton > Rest Position. A-pose is fine. (The
     offset is relative to the volume, so it does not matter what pose the animation uses, but the
     point you place must be placed against the rest pose.)
  3. Place the point: put the 3D cursor there, or select a cube / empty whose origin is there.
  4. Pick the volume: make its bone the active bone (if the rig has bones named like the volumes),
     or set VOLUME below.
  5. Run the script (Text Editor > Run Script). The result is printed to the system console,
     shown in a popup and copied to the clipboard, ready to paste into Anim Hacker.

The script works out where your rig sits (orientation, scale, position) by matching its joint
bones to the default skeleton. Joints that are posed differently, such as the arms of an A-pose
rig, are set aside automatically, and each volume's own orientation is taken from the joint it is
attached to, so an A-pose rig gives the same offsets as a T-pose one. If the rig has a bone named
like the volume (L_HAND, HEAD, ...), that bone's head is used as the volume's centre; otherwise the
centre is worked out from the rig's joints. The volume's size always comes from the default
skeleton, so the rig should have the default shape. The script reports how well everything matched,
and warns if a volume bone is not where the default skeleton puts it.
"""
import math

# The collision volume the offset is measured from (used unless a bone named like a volume is the
# active bone). One of: PELVIS BUTT BELLY LEFT_HANDLE RIGHT_HANDLE LOWER_BACK CHEST LEFT_PEC
# RIGHT_PEC UPPER_BACK NECK HEAD L_CLAVICLE L_UPPER_ARM L_LOWER_ARM L_HAND R_CLAVICLE
# R_UPPER_ARM R_LOWER_ARM R_HAND R_UPPER_LEG R_LOWER_LEG R_FOOT L_UPPER_LEG L_LOWER_LEG L_FOOT
VOLUME = "L_HAND"

# A match worse than this (in metres of skeleton) means the rig is not the default skeleton.
MAX_GOOD_FIT_ERROR = 0.02
MIN_MATCHED_JOINTS = 6
# Joints that fit worse than this are dropped when finding the rig's overall orientation.
TRIM_TARGET = 0.005
# A joint whose neighbours lie within this ratio of a straight line is treated as straight.
COLLINEAR = 0.05
# A volume bone further than this (metres) from the default skeleton's volume centre is reported.
MAX_CENTRE_ERROR = 0.03

# --- BEGIN GENERATED DATA (tools/gen_blender_data.py) ---
# Joint name -> rest position in skeleton space (metres)
JOINTS = {
    'mPelvis': (0, 0, 1.067),
    'mSpine1': (0, 0, 1.151),
    'mSpine2': (0, 0, 1.067),
    'mTorso': (0, 0, 1.151),
    'mSpine3': (-0.015, 0, 1.356),
    'mSpine4': (0, 0, 1.151),
    'mChest': (-0.015, 0, 1.356),
    'mNeck': (-0.025, 0, 1.607),
    'mHead': (-0.025, 0, 1.683),
    'mSkull': (-0.025, 0, 1.762),
    'mEyeRight': (0.073, -0.036, 1.762),
    'mEyeLeft': (0.073, 0.036, 1.762),
    'mFaceRoot': (0, 0, 1.728),
    'mFaceEyeAltRight': (0.073, -0.036, 1.762),
    'mFaceEyeAltLeft': (0.073, 0.036, 1.762),
    'mFaceForeheadLeft': (0.061, 0.035, 1.811),
    'mFaceForeheadRight': (0.061, -0.035, 1.811),
    'mFaceEyebrowOuterLeft': (0.064, 0.051, 1.776),
    'mFaceEyebrowCenterLeft': (0.07, 0.043, 1.784),
    'mFaceEyebrowInnerLeft': (0.075, 0.022, 1.779),
    'mFaceEyebrowOuterRight': (0.064, -0.051, 1.776),
    'mFaceEyebrowCenterRight': (0.07, -0.043, 1.784),
    'mFaceEyebrowInnerRight': (0.075, -0.022, 1.779),
    'mFaceEyeLidUpperLeft': (0.073, 0.036, 1.762),
    'mFaceEyeLidLowerLeft': (0.073, 0.036, 1.762),
    'mFaceEyeLidUpperRight': (0.073, -0.036, 1.762),
    'mFaceEyeLidLowerRight': (0.073, -0.036, 1.762),
    'mFaceEar1Left': (0, 0.08, 1.73),
    'mFaceEar2Left': (-0.019, 0.098, 1.755),
    'mFaceEar1Right': (0, -0.08, 1.73),
    'mFaceEar2Right': (-0.019, -0.098, 1.755),
    'mFaceNoseLeft': (0.086, 0.015, 1.724),
    'mFaceNoseCenter': (0.102, 0, 1.728),
    'mFaceNoseRight': (0.086, -0.015, 1.724),
    'mFaceCheekLowerLeft': (0.05, 0.034, 1.697),
    'mFaceCheekUpperLeft': (0.07, 0.034, 1.723),
    'mFaceCheekLowerRight': (0.05, -0.034, 1.697),
    'mFaceCheekUpperRight': (0.07, -0.034, 1.723),
    'mFaceJaw': (-0.001, 0, 1.713),
    'mFaceChin': (0.073, 0, 1.659),
    'mFaceTeethLower': (0.02, 0, 1.674),
    'mFaceLipLowerLeft': (0.065, 0, 1.674),
    'mFaceLipLowerRight': (0.065, 0, 1.674),
    'mFaceLipLowerCenter': (0.065, 0, 1.674),
    'mFaceTongueBase': (0.059, 0, 1.679),
    'mFaceTongueTip': (0.081, 0, 1.686),
    'mFaceJawShaper': (0, 0, 1.728),
    'mFaceForeheadCenter': (0.069, 0, 1.793),
    'mFaceNoseBase': (0.094, 0, 1.712),
    'mFaceTeethUpper': (0.02, 0, 1.698),
    'mFaceLipUpperLeft': (0.065, 0, 1.695),
    'mFaceLipUpperRight': (0.065, 0, 1.695),
    'mFaceLipCornerLeft': (0.048, -0.019, 1.688),
    'mFaceLipCornerRight': (0.048, 0.019, 1.688),
    'mFaceLipUpperCenter': (0.065, 0, 1.695),
    'mFaceEyecornerInnerLeft': (0.075, 0.017, 1.76),
    'mFaceEyecornerInnerRight': (0.075, -0.017, 1.76),
    'mFaceNoseBridge': (0.091, 0, 1.748),
    'mCollarLeft': (-0.036, 0.085, 1.521),
    'mShoulderLeft': (-0.036, 0.164, 1.521),
    'mElbowLeft': (-0.036, 0.412, 1.521),
    'mWristLeft': (-0.036, 0.617, 1.521),
    'mHandMiddle1Left': (-0.023, 0.718, 1.536),
    'mHandMiddle2Left': (-0.024, 0.758, 1.53),
    'mHandMiddle3Left': (-0.025, 0.807, 1.522),
    'mHandIndex1Left': (0.002, 0.714, 1.536),
    'mHandIndex2Left': (0.019, 0.75, 1.53),
    'mHandIndex3Left': (0.033, 0.782, 1.524),
    'mHandRing1Left': (-0.046, 0.716, 1.53),
    'mHandRing2Left': (-0.059, 0.754, 1.522),
    'mHandRing3Left': (-0.072, 0.794, 1.513),
    'mHandPinky1Left': (-0.067, 0.712, 1.524),
    'mHandPinky2Left': (-0.091, 0.737, 1.518),
    'mHandPinky3Left': (-0.106, 0.755, 1.514),
    'mHandThumb1Left': (-0.005, 0.643, 1.525),
    'mHandThumb2Left': (0.023, 0.675, 1.524),
    'mHandThumb3Left': (0.046, 0.706, 1.523),
    'mCollarRight': (-0.036, -0.085, 1.521),
    'mShoulderRight': (-0.036, -0.164, 1.521),
    'mElbowRight': (-0.036, -0.412, 1.521),
    'mWristRight': (-0.036, -0.617, 1.521),
    'mHandMiddle1Right': (-0.023, -0.718, 1.536),
    'mHandMiddle2Right': (-0.024, -0.758, 1.53),
    'mHandMiddle3Right': (-0.025, -0.807, 1.522),
    'mHandIndex1Right': (0.002, -0.714, 1.536),
    'mHandIndex2Right': (0.019, -0.75, 1.53),
    'mHandIndex3Right': (0.033, -0.782, 1.524),
    'mHandRing1Right': (-0.046, -0.716, 1.53),
    'mHandRing2Right': (-0.059, -0.754, 1.522),
    'mHandRing3Right': (-0.072, -0.794, 1.513),
    'mHandPinky1Right': (-0.067, -0.712, 1.524),
    'mHandPinky2Right': (-0.091, -0.737, 1.518),
    'mHandPinky3Right': (-0.106, -0.755, 1.514),
    'mHandThumb1Right': (-0.005, -0.643, 1.525),
    'mHandThumb2Right': (0.023, -0.675, 1.524),
    'mHandThumb3Right': (0.046, -0.706, 1.523),
    'mWingsRoot': (-0.029, 0, 1.356),
    'mWing1Left': (-0.128, 0.105, 1.537),
    'mWing2Left': (-0.296, 0.274, 1.604),
    'mWing3Left': (-0.477, 0.457, 1.604),
    'mWing4Left': (-0.648, 0.63, 1.604),
    'mWing4FanLeft': (-0.648, 0.63, 1.604),
    'mWing1Right': (-0.128, -0.105, 1.537),
    'mWing2Right': (-0.296, -0.274, 1.604),
    'mWing3Right': (-0.477, -0.457, 1.604),
    'mWing4Right': (-0.648, -0.63, 1.604),
    'mWing4FanRight': (-0.648, -0.63, 1.604),
    'mHipRight': (0.034, -0.129, 1.026),
    'mKneeRight': (0.033, -0.08, 0.535),
    'mAnkleRight': (0.004, -0.08, 0.067),
    'mFootRight': (0.116, -0.08, 0.006),
    'mToeRight': (0.225, -0.08, 0.006),
    'mHipLeft': (0.034, 0.127, 1.026),
    'mKneeLeft': (0.033, 0.081, 0.535),
    'mAnkleLeft': (0.004, 0.082, 0.067),
    'mFootLeft': (0.116, 0.082, 0.006),
    'mToeLeft': (0.225, 0.082, 0.006),
    'mTail1': (-0.116, 0, 1.114),
    'mTail2': (-0.313, 0, 1.114),
    'mTail3': (-0.481, 0, 1.114),
    'mTail4': (-0.623, 0, 1.114),
    'mTail5': (-0.735, 0, 1.114),
    'mTail6': (-0.829, 0, 1.114),
    'mGroin': (0.064, 0, 0.97),
    'mHindLimbsRoot': (-0.2, 0, 1.151),
    'mHindLimb1Left': (-0.404, 0.129, 1.026),
    'mHindLimb2Left': (-0.402, 0.083, 0.535),
    'mHindLimb3Left': (-0.432, 0.08, 0.067),
    'mHindLimb4Left': (-0.32, 0.08, 0.006),
    'mHindLimb1Right': (-0.404, -0.129, 1.026),
    'mHindLimb2Right': (-0.402, -0.083, 0.535),
    'mHindLimb3Right': (-0.432, -0.08, 0.067),
    'mHindLimb4Right': (-0.32, -0.08, 0.006),
}

# Joint name -> its parent joint (the root has none)
JOINT_PARENT = {
    'mSpine1': 'mPelvis',
    'mSpine2': 'mSpine1',
    'mTorso': 'mSpine2',
    'mSpine3': 'mTorso',
    'mSpine4': 'mSpine3',
    'mChest': 'mSpine4',
    'mNeck': 'mChest',
    'mHead': 'mNeck',
    'mSkull': 'mHead',
    'mEyeRight': 'mHead',
    'mEyeLeft': 'mHead',
    'mFaceRoot': 'mHead',
    'mFaceEyeAltRight': 'mFaceRoot',
    'mFaceEyeAltLeft': 'mFaceRoot',
    'mFaceForeheadLeft': 'mFaceRoot',
    'mFaceForeheadRight': 'mFaceRoot',
    'mFaceEyebrowOuterLeft': 'mFaceRoot',
    'mFaceEyebrowCenterLeft': 'mFaceRoot',
    'mFaceEyebrowInnerLeft': 'mFaceRoot',
    'mFaceEyebrowOuterRight': 'mFaceRoot',
    'mFaceEyebrowCenterRight': 'mFaceRoot',
    'mFaceEyebrowInnerRight': 'mFaceRoot',
    'mFaceEyeLidUpperLeft': 'mFaceRoot',
    'mFaceEyeLidLowerLeft': 'mFaceRoot',
    'mFaceEyeLidUpperRight': 'mFaceRoot',
    'mFaceEyeLidLowerRight': 'mFaceRoot',
    'mFaceEar1Left': 'mFaceRoot',
    'mFaceEar2Left': 'mFaceEar1Left',
    'mFaceEar1Right': 'mFaceRoot',
    'mFaceEar2Right': 'mFaceEar1Right',
    'mFaceNoseLeft': 'mFaceRoot',
    'mFaceNoseCenter': 'mFaceRoot',
    'mFaceNoseRight': 'mFaceRoot',
    'mFaceCheekLowerLeft': 'mFaceRoot',
    'mFaceCheekUpperLeft': 'mFaceRoot',
    'mFaceCheekLowerRight': 'mFaceRoot',
    'mFaceCheekUpperRight': 'mFaceRoot',
    'mFaceJaw': 'mFaceRoot',
    'mFaceChin': 'mFaceJaw',
    'mFaceTeethLower': 'mFaceJaw',
    'mFaceLipLowerLeft': 'mFaceTeethLower',
    'mFaceLipLowerRight': 'mFaceTeethLower',
    'mFaceLipLowerCenter': 'mFaceTeethLower',
    'mFaceTongueBase': 'mFaceTeethLower',
    'mFaceTongueTip': 'mFaceTongueBase',
    'mFaceJawShaper': 'mFaceRoot',
    'mFaceForeheadCenter': 'mFaceRoot',
    'mFaceNoseBase': 'mFaceRoot',
    'mFaceTeethUpper': 'mFaceRoot',
    'mFaceLipUpperLeft': 'mFaceTeethUpper',
    'mFaceLipUpperRight': 'mFaceTeethUpper',
    'mFaceLipCornerLeft': 'mFaceTeethUpper',
    'mFaceLipCornerRight': 'mFaceTeethUpper',
    'mFaceLipUpperCenter': 'mFaceTeethUpper',
    'mFaceEyecornerInnerLeft': 'mFaceRoot',
    'mFaceEyecornerInnerRight': 'mFaceRoot',
    'mFaceNoseBridge': 'mFaceRoot',
    'mCollarLeft': 'mChest',
    'mShoulderLeft': 'mCollarLeft',
    'mElbowLeft': 'mShoulderLeft',
    'mWristLeft': 'mElbowLeft',
    'mHandMiddle1Left': 'mWristLeft',
    'mHandMiddle2Left': 'mHandMiddle1Left',
    'mHandMiddle3Left': 'mHandMiddle2Left',
    'mHandIndex1Left': 'mWristLeft',
    'mHandIndex2Left': 'mHandIndex1Left',
    'mHandIndex3Left': 'mHandIndex2Left',
    'mHandRing1Left': 'mWristLeft',
    'mHandRing2Left': 'mHandRing1Left',
    'mHandRing3Left': 'mHandRing2Left',
    'mHandPinky1Left': 'mWristLeft',
    'mHandPinky2Left': 'mHandPinky1Left',
    'mHandPinky3Left': 'mHandPinky2Left',
    'mHandThumb1Left': 'mWristLeft',
    'mHandThumb2Left': 'mHandThumb1Left',
    'mHandThumb3Left': 'mHandThumb2Left',
    'mCollarRight': 'mChest',
    'mShoulderRight': 'mCollarRight',
    'mElbowRight': 'mShoulderRight',
    'mWristRight': 'mElbowRight',
    'mHandMiddle1Right': 'mWristRight',
    'mHandMiddle2Right': 'mHandMiddle1Right',
    'mHandMiddle3Right': 'mHandMiddle2Right',
    'mHandIndex1Right': 'mWristRight',
    'mHandIndex2Right': 'mHandIndex1Right',
    'mHandIndex3Right': 'mHandIndex2Right',
    'mHandRing1Right': 'mWristRight',
    'mHandRing2Right': 'mHandRing1Right',
    'mHandRing3Right': 'mHandRing2Right',
    'mHandPinky1Right': 'mWristRight',
    'mHandPinky2Right': 'mHandPinky1Right',
    'mHandPinky3Right': 'mHandPinky2Right',
    'mHandThumb1Right': 'mWristRight',
    'mHandThumb2Right': 'mHandThumb1Right',
    'mHandThumb3Right': 'mHandThumb2Right',
    'mWingsRoot': 'mChest',
    'mWing1Left': 'mWingsRoot',
    'mWing2Left': 'mWing1Left',
    'mWing3Left': 'mWing2Left',
    'mWing4Left': 'mWing3Left',
    'mWing4FanLeft': 'mWing3Left',
    'mWing1Right': 'mWingsRoot',
    'mWing2Right': 'mWing1Right',
    'mWing3Right': 'mWing2Right',
    'mWing4Right': 'mWing3Right',
    'mWing4FanRight': 'mWing3Right',
    'mHipRight': 'mPelvis',
    'mKneeRight': 'mHipRight',
    'mAnkleRight': 'mKneeRight',
    'mFootRight': 'mAnkleRight',
    'mToeRight': 'mFootRight',
    'mHipLeft': 'mPelvis',
    'mKneeLeft': 'mHipLeft',
    'mAnkleLeft': 'mKneeLeft',
    'mFootLeft': 'mAnkleLeft',
    'mToeLeft': 'mFootLeft',
    'mTail1': 'mPelvis',
    'mTail2': 'mTail1',
    'mTail3': 'mTail2',
    'mTail4': 'mTail3',
    'mTail5': 'mTail4',
    'mTail6': 'mTail5',
    'mGroin': 'mPelvis',
    'mHindLimbsRoot': 'mPelvis',
    'mHindLimb1Left': 'mHindLimbsRoot',
    'mHindLimb2Left': 'mHindLimb1Left',
    'mHindLimb3Left': 'mHindLimb2Left',
    'mHindLimb4Left': 'mHindLimb3Left',
    'mHindLimb1Right': 'mHindLimbsRoot',
    'mHindLimb2Right': 'mHindLimb1Right',
    'mHindLimb3Right': 'mHindLimb2Right',
    'mHindLimb4Right': 'mHindLimb3Right',
}

# Collision volume -> the joint it is attached to
VOLUME_PARENT = {
    'PELVIS': 'mPelvis',
    'BUTT': 'mPelvis',
    'BELLY': 'mTorso',
    'LEFT_HANDLE': 'mTorso',
    'RIGHT_HANDLE': 'mTorso',
    'LOWER_BACK': 'mTorso',
    'CHEST': 'mChest',
    'LEFT_PEC': 'mChest',
    'RIGHT_PEC': 'mChest',
    'UPPER_BACK': 'mChest',
    'NECK': 'mNeck',
    'HEAD': 'mHead',
    'L_CLAVICLE': 'mCollarLeft',
    'L_UPPER_ARM': 'mShoulderLeft',
    'L_LOWER_ARM': 'mElbowLeft',
    'L_HAND': 'mWristLeft',
    'R_CLAVICLE': 'mCollarRight',
    'R_UPPER_ARM': 'mShoulderRight',
    'R_LOWER_ARM': 'mElbowRight',
    'R_HAND': 'mWristRight',
    'R_UPPER_LEG': 'mHipRight',
    'R_LOWER_LEG': 'mKneeRight',
    'R_FOOT': 'mAnkleRight',
    'L_UPPER_LEG': 'mHipLeft',
    'L_LOWER_LEG': 'mKneeLeft',
    'L_FOOT': 'mAnkleLeft',
}

# Collision volume -> (centre, rotation as x y z w, size) at rest, in skeleton space
VOLUMES = {
    'PELVIS': ((-0.01, 0, 1.047), (0, 0.06975647, 0, 0.9975641), (0.12, 0.16, 0.17)),
    'BUTT': ((-0.06, 0, 0.967), (0, 0, 0, 1), (0.1, 0.1, 0.1)),
    'BELLY': ((0.028, 0, 1.191), (0, 0.06975647, 0, 0.9975641), (0.09, 0.13, 0.15)),
    'LEFT_HANDLE': ((0, 0.1, 1.209), (0, 0, 0, 1), (0.05, 0.05, 0.05)),
    'RIGHT_HANDLE': ((0, -0.1, 1.209), (0, 0, 0, 1), (0.05, 0.05, 0.05)),
    'LOWER_BACK': ((0, 0, 1.174), (0, 0, 0, 1), (0.09, 0.13, 0.15)),
    'CHEST': ((0.013, 0, 1.426), (0, -0.08715574, 0, 0.9961947), (0.11, 0.15, 0.2)),
    'LEFT_PEC': ((0.104, 0.082, 1.398), (0, 0.03742857, 0, 0.9992993), (0.05, 0.05, 0.05)),
    'RIGHT_PEC': ((0.104, -0.082, 1.398), (0, 0.03742857, 0, 0.9992993), (0.05, 0.05, 0.05)),
    'UPPER_BACK': ((-0.015, 0, 1.373), (0, 0, 0, 1), (0.09, 0.13, 0.15)),
    'NECK': ((-0.025, 0, 1.627), (0, 0, 0, 1), (0.05, 0.06, 0.08)),
    'HEAD': ((-0.005, 0, 1.753), (0, 0, 0, 1), (0.11, 0.09, 0.12)),
    'L_CLAVICLE': ((-0.016, 0.085, 1.541), (0, 0, 0, 1), (0.07, 0.14, 0.05)),
    'L_UPPER_ARM': ((-0.036, 0.284, 1.531), (-0.04361939, 0, 0, 0.9990482), (0.05, 0.17, 0.05)),
    'L_LOWER_ARM': ((-0.036, 0.512, 1.521), (-0.02617695, 0, 0, 0.9996573), (0.04, 0.14, 0.04)),
    'L_HAND': ((-0.026, 0.667, 1.521), (-0.02607734, 0.002281471, -0.08712588, 0.9958533), (0.05, 0.08, 0.03)),
    'R_CLAVICLE': ((-0.016, -0.085, 1.541), (0, 0, 0, 1), (0.07, 0.14, 0.05)),
    'R_UPPER_ARM': ((-0.036, -0.284, 1.531), (0.04361939, 0, 0, 0.9990482), (0.05, 0.17, 0.05)),
    'R_LOWER_ARM': ((-0.036, -0.512, 1.521), (0.02617695, 0, 0, 0.9996573), (0.04, 0.14, 0.04)),
    'R_HAND': ((-0.026, -0.667, 1.521), (0.02607734, 0.002281471, 0.08712588, 0.9958533), (0.05, 0.08, 0.03)),
    'R_UPPER_LEG': ((0.014, -0.079, 0.806), (0, 0, 0, 1), (0.09, 0.09, 0.32)),
    'R_LOWER_LEG': ((0.013, -0.08, 0.335), (0, 0, 0, 1), (0.06, 0.06, 0.25)),
    'R_FOOT': ((0.081, -0.08, 0.026), (0, 0.08715574, 0, 0.9961947), (0.13, 0.05, 0.05)),
    'L_UPPER_LEG': ((0.014, 0.077, 0.806), (0, 0, 0, 1), (0.09, 0.09, 0.32)),
    'L_LOWER_LEG': ((0.013, 0.081, 0.335), (0, 0, 0, 1), (0.06, 0.06, 0.25)),
    'L_FOOT': ((0.081, 0.082, 0.026), (0, 0.08715574, 0, 0.9961947), (0.13, 0.05, 0.05)),
}
# --- END GENERATED DATA ---


# ------------------------------------------------------------------------------ maths (no Blender)

def _rotate(v, q):
    """The viewer's (vector * quaternion): rotates v by q = (x, y, z, w)."""
    qx, qy, qz, qw = q
    rw = -qx * v[0] - qy * v[1] - qz * v[2]
    rx = qw * v[0] + qy * v[2] - qz * v[1]
    ry = qw * v[1] + qz * v[0] - qx * v[2]
    rz = qw * v[2] + qx * v[1] - qy * v[0]
    return (-rw * qx + rx * qw - ry * qz + rz * qy,
            -rw * qy + ry * qw - rz * qx + rx * qz,
            -rw * qz + rz * qw - rx * qy + ry * qx)


def _conjugate(q):
    return (-q[0], -q[1], -q[2], q[3])


def fit_similarity(skeleton_points, rig_points):
    """Finds the scale s, rotation R (3x3) and translation t with rig = s * R @ skeleton + t that
    best matches two lists of corresponding points. Returns (s, R, t, rms) where rms is the
    remaining error in skeleton units. Raises ValueError if the points cannot be matched."""
    import numpy as np

    a = np.asarray(skeleton_points, dtype=float)
    b = np.asarray(rig_points, dtype=float)
    if len(a) < MIN_MATCHED_JOINTS:
        raise ValueError("only %d joints matched the default skeleton; at least %d are needed"
                         % (len(a), MIN_MATCHED_JOINTS))
    ca, cb = a.mean(axis=0), b.mean(axis=0)
    a0, b0 = a - ca, b - cb
    spread = float((a0 ** 2).sum())
    if spread < 1e-9:
        raise ValueError("the matched joints are all in the same place")
    u, sing, vt = np.linalg.svd(a0.T @ b0)
    if sing[1] < 1e-6 * sing[0]:
        raise ValueError("the matched joints lie in a line")
    sign = 1.0 if np.linalg.det(vt.T @ u.T) >= 0 else -1.0       # never accept a mirror image
    d = np.diag([1.0, 1.0, sign])
    rot = vt.T @ d @ u.T
    scale = float((sing * np.array([1.0, 1.0, sign])).sum() / spread)
    if scale <= 0:
        raise ValueError("the rig cannot be matched to the default skeleton")
    trans = cb - scale * rot @ ca
    err = (scale * (a @ rot.T) + trans) - b
    rms = math.sqrt(float((err ** 2).sum() / len(a))) / scale
    return scale, rot, trans, rms


def volume_offset(point_in_skeleton_space, volume):
    """The offset that the viewer's getVolumePos() turns back into this point: subtract the volume's
    centre, rotate into the volume's own frame, divide by the volume's size."""
    centre, rotation, size = VOLUMES[volume]
    delta = tuple(point_in_skeleton_space[i] - centre[i] for i in range(3))
    local = _rotate(delta, _conjugate(rotation))
    return tuple(local[i] / size[i] for i in range(3))


def format_offset(offset):
    parts = []
    for v in offset:
        text = ("%.6f" % v).rstrip("0").rstrip(".")
        parts.append("0" if text in ("", "-0") else text)
    return "<%s>" % ",".join(parts)


def fit_core(rig_joints):
    """Fits the rig's overall position, orientation and scale to the default skeleton, ignoring the
    joints that are posed differently (the arms of an A-pose rig, say): the worst-fitting joints
    are dropped until the rest agree. Returns (fit, joints_used, joints_ignored)."""
    names = [n for n in JOINTS if n in rig_joints]
    if len(names) < MIN_MATCHED_JOINTS:
        raise ValueError("only %d joints matched the default skeleton; at least %d are needed"
                         % (len(names), MIN_MATCHED_JOINTS))
    keep = list(names)
    floor = max(MIN_MATCHED_JOINTS, int(0.6 * len(names)))
    while True:
        fit = fit_similarity([JOINTS[n] for n in keep], [rig_joints[n] for n in keep])
        if fit[3] <= TRIM_TARGET or len(keep) <= floor:
            return fit, keep, [n for n in names if n not in keep]
        scale, rot, trans, _rms = fit
        error = {n: float(((scale * rot @ _vec(JOINTS[n]) + trans - _vec(rig_joints[n])) ** 2).sum())
                 for n in keep}
        drop = min(max(1, len(keep) // 20), len(keep) - floor)
        worst = set(sorted(keep, key=error.get, reverse=True)[:drop])
        keep = [n for n in keep if n not in worst]


def _vec(p):
    import numpy as np
    return np.asarray(p, dtype=float)


def joint_rotation(joint, rig_joints, fit):
    """The rotation (3x3, skeleton space -> rig space) of one joint in the rig, found from where its
    neighbouring joints (parent and children) are. A joint whose neighbours all lie on one line, such
    as an elbow, has its twist taken from the overall rig orientation and is turned by the shortest
    way onto the direction it points in the rig."""
    import numpy as np
    scale, rot, _trans, _rms = fit
    neighbours = [n for n in JOINTS if JOINT_PARENT.get(n) == joint]
    if joint in JOINT_PARENT:
        neighbours.append(JOINT_PARENT[joint])
    pairs = []
    for n in neighbours:
        if n in rig_joints and joint in rig_joints:
            a = rot @ (_vec(JOINTS[n]) - _vec(JOINTS[joint]))          # where it would be without a pose
            b = (_vec(rig_joints[n]) - _vec(rig_joints[joint])) / scale
            if np.linalg.norm(a) > 1e-4 and np.linalg.norm(b) > 1e-4:
                pairs.append((a, b))
    if not pairs:
        return rot
    a = np.array([p[0] for p in pairs])
    b = np.array([p[1] for p in pairs])
    u, sing, vt = np.linalg.svd(a.T @ b)
    if sing[1] > COLLINEAR * sing[0]:
        sign = 1.0 if np.linalg.det(vt.T @ u.T) >= 0 else -1.0
        turn = vt.T @ np.diag([1.0, 1.0, sign]) @ u.T
    else:
        longest = max(range(len(pairs)), key=lambda i: np.linalg.norm(a[i]))
        turn = _shortest_arc(a[longest], b[longest])
    return turn @ rot


def _shortest_arc(a, b):
    import numpy as np
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    axis = np.cross(a, b)
    s, c = float(np.linalg.norm(axis)), float(a @ b)
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        helper = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
        axis = np.cross(a, helper)
        axis /= np.linalg.norm(axis)
        return 2.0 * np.outer(axis, axis) - np.eye(3)
    axis /= s
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + s * k + (1.0 - c) * (k @ k)


class Result:
    """offset: the answer; fit_error: metres of skeleton the core joints disagree by; used/ignored:
    joint names; centre_error: how far (metres of skeleton) the rig's volume bone is from where the
    default skeleton puts the volume, or None if the rig has no bone for it."""
    def __init__(self, offset, fit_error, used, ignored, centre_error):
        self.offset, self.fit_error, self.used, self.ignored, self.centre_error = (
            offset, fit_error, used, ignored, centre_error)


def compute(point_in_rig_space, rig_joints, volume, rig_volume_head=None):
    """Everything together. rig_joints maps joint name -> position in the rig's space;
    rig_volume_head is the position of the rig's own bone for this volume, if it has one (it is then
    the volume's centre; otherwise the centre comes from the default skeleton)."""
    import numpy as np
    if volume not in VOLUMES:
        raise ValueError("'%s' is not a collision volume. Valid names: %s" % (volume, ", ".join(VOLUMES)))
    fit, used, ignored = fit_core(rig_joints)
    scale = fit[0]
    parent = VOLUME_PARENT[volume]
    centre, rotation, size = VOLUMES[volume]
    if parent in rig_joints:
        rot = joint_rotation(parent, rig_joints, fit)
        predicted = _vec(rig_joints[parent]) + scale * rot @ (_vec(centre) - _vec(JOINTS[parent]))
    else:
        rot = fit[1]
        predicted = scale * rot @ _vec(centre) + fit[2]
    if rig_volume_head is not None:
        head = _vec(rig_volume_head)
        centre_error = float(np.linalg.norm(head - predicted)) / scale
    else:
        head, centre_error = predicted, None
    local = rot.T @ ((_vec(point_in_rig_space) - head) / scale)           # in skeleton orientation
    in_volume = _rotate(tuple(local), _conjugate(rotation))
    offset = tuple(in_volume[i] / size[i] for i in range(3))
    return Result(offset, fit[3], used, ignored, centre_error)


# ------------------------------------------------------------------------------------- Blender part

def _find_armature(context):
    active = context.active_object
    candidates = [active] if active is not None and active.type == "ARMATURE" else []
    candidates += [o for o in context.view_layer.objects if o.type == "ARMATURE" and o not in candidates]
    for obj in candidates:
        if sum(1 for b in obj.data.bones if b.name in JOINTS) >= MIN_MATCHED_JOINTS:
            return obj
    raise ValueError("No armature with the standard Second Life joint bones (mPelvis, mHead, ...) "
                     "was found in this scene.")


def _find_point(context, armature):
    others = [o for o in context.selected_objects if o != armature and o.type != "ARMATURE"]
    if others:
        obj = context.active_object if context.active_object in others else others[0]
        return obj.matrix_world.translation.copy(), "the origin of '%s'" % obj.name
    return context.scene.cursor.location.copy(), "the 3D cursor"


def _find_volume(armature):
    active = armature.data.bones.active
    if active is not None and active.name in VOLUMES:
        return active.name, "the active bone"
    return VOLUME, "VOLUME in the script"


def main():
    import bpy

    context = bpy.context
    try:
        armature = _find_armature(context)
        point, point_from = _find_point(context, armature)
        volume, volume_from = _find_volume(armature)
        world = armature.matrix_world
        joints = {b.name: tuple(world @ b.head_local) for b in armature.data.bones if b.name in JOINTS}
        volume_bone = next((b for b in armature.data.bones if b.name == volume), None)
        head = tuple(world @ volume_bone.head_local) if volume_bone is not None else None
        result = compute(tuple(point), joints, volume, head)
    except ValueError as exc:
        message = "Anim Hacker offset: %s" % exc
        print(message)
        _popup(context, ["Could not work out the offset", str(exc)], "ERROR")
        return

    offset, rms = result.offset, result.fit_error
    text = format_offset(offset)
    lines = ["Offset from %s: %s" % (volume, text),
             "Point: %s; volume: %s (%s)" % (point_from, volume, volume_from),
             "Volume centre: %s" % ("the rig's '%s' bone" % volume if head is not None
                                    else "worked out from the rig's joints"),
             "Rig orientation fitted on %d joints (%d ignored as posed differently), error %.1f mm"
             % (len(result.used), len(result.ignored), rms * 1000)]
    bad = rms > MAX_GOOD_FIT_ERROR
    if bad:
        lines.append("WARNING: poor match. Is the rig the default skeleton shape?")
    if result.centre_error is not None and result.centre_error > MAX_CENTRE_ERROR:
        bad = True
        lines.append("WARNING: the '%s' bone is %.0f mm from where the default skeleton puts it."
                     % (volume, result.centre_error * 1000))
    if max(abs(v) for v in offset) > 2.0:
        lines.append("Note: the point is well outside the volume (offsets are in units of its size).")
    print("\n".join(lines))
    try:
        context.window_manager.clipboard = text
        lines.append("(copied to the clipboard)")
    except Exception:
        pass
    _popup(context, lines, "ERROR" if bad else "INFO")


def _popup(context, lines, icon):
    def draw(self, _context):
        for line in lines:
            self.layout.label(text=line)
    try:
        context.window_manager.popup_menu(draw, title="Anim Hacker offset", icon=icon)
    except Exception:
        pass


try:
    import bpy  # noqa: F401
except ImportError:
    pass                     # imported for testing outside Blender
else:
    main()
