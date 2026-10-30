"""The lab's registered datasets, until the executor's dataset registry exists.

NYU Depth V2 follows the lab's data contract (legacy/data_contract.json: 50,688 training and
654 validation frames, RGB uint8 at 480x640, depth float32 in metres). Versions match the ones
demo experiments record in their provenance. Checksums are generated from id and version.
"""

from datetime import UTC, datetime

from agentic_api.demo._seed import sha256_hex
from agentic_api.schemas import DataContractOut, DatasetOut, DatasetSplitOut


def _dataset(
    *,
    id: str,
    name: str,
    version: str,
    tasks: list[str],
    modality: str,
    scenes: str,
    description: str,
    size: tuple[int, int],
    splits: dict[str, int],
    size_bytes: int,
    license: str,
    homepage: str | None,
    registered_at: datetime,
    contract: DataContractOut,
) -> DatasetOut:
    width, height = size
    return DatasetOut(
        id=id,
        name=name,
        version=version,
        tasks=tasks,
        modality=modality,
        scenes=scenes,
        description=description,
        width=width,
        height=height,
        samples=sum(splits.values()),
        splits=[DatasetSplitOut(name=split, samples=count) for split, count in splits.items()],
        size_bytes=size_bytes,
        license=license,
        homepage=homepage,
        mount_path=f"/datasets/{id}/{version}",
        checksum_sha256=sha256_hex("dataset", id, version),
        registered_at=registered_at,
        contract=contract,
        demo=True,
    )


DATASETS: tuple[DatasetOut, ...] = (
    _dataset(
        id="nyu2",
        name="NYU Depth V2",
        version="2025.03",
        tasks=["monocular_depth", "semantic_segmentation"],
        modality="RGB-D (Microsoft Kinect)",
        scenes="indoor",
        description=(
            "Indoor scenes from 464 rooms in three cities, recorded with a Microsoft Kinect: "
            "1,449 densely labelled pairs of aligned RGB and depth images and about 407k raw "
            "frames. The lab's copy holds the 50,688 synchronized frames used for depth "
            "training and the 654 labelled test pairs, used for validation."
        ),
        size=(640, 480),
        splits={"train": 50_688, "val": 654, "test": 0},
        size_bytes=20_318_412_800,
        license="Non-commercial research use (NYU Depth V2 terms)",
        homepage="https://cs.nyu.edu/~fergus/datasets/nyu_depth_v2.html",
        registered_at=datetime(2026, 5, 30, 7, 36, 29, tzinfo=UTC),
        contract=DataContractOut(
            inputs="RGB uint8, 3x480x640",
            targets="Depth map float32, 480x640",
            units="metres",
            valid_range="0.001 to 10 m",
            missing_values="0 where the sensor returned no depth",
            evaluation="Eigen crop, depth capped at 10 m; AbsRel, RMSE and delta1",
        ),
    ),
    _dataset(
        id="kitti",
        name="KITTI depth (Eigen split)",
        version="eigen-2014",
        tasks=["monocular_depth", "depth_completion"],
        modality="RGB and LiDAR (Velodyne HDL-64E)",
        scenes="outdoor driving",
        description=(
            "Driving sequences recorded around Karlsruhe, with LiDAR scans projected into the "
            "left camera as sparse depth. The Eigen split has 23,158 training and 697 test "
            "images; about 5% of the pixels have ground truth."
        ),
        size=(1216, 352),
        splits={"train": 23_158, "val": 0, "test": 697},
        size_bytes=66_571_993_088,
        license="CC BY-NC-SA 3.0",
        homepage="https://www.cvlibs.net/datasets/kitti/eval_depth.php",
        registered_at=datetime(2026, 6, 18, 2, 12, 5, tzinfo=UTC),
        contract=DataContractOut(
            inputs="RGB uint8, 3x352x1216 (the benchmark crop)",
            targets="Sparse depth map float32, 352x1216, from projected LiDAR points",
            units="metres",
            valid_range="0.001 to 80 m",
            missing_values="0 where no LiDAR point projects",
            evaluation="Garg crop, depth capped at 80 m; AbsRel, RMSE and delta1",
        ),
    ),
    _dataset(
        id="sunrgbd",
        name="SUN RGB-D",
        version="2015.1",
        tasks=["monocular_depth", "semantic_segmentation"],
        modality="RGB-D (Kinect v1 and v2, Intel RealSense, Asus Xtion)",
        scenes="indoor",
        description=(
            "10,335 RGB-D images of indoor scenes captured with four different sensors, with "
            "37-class segmentation labels. Useful for checking that a model trained on one "
            "sensor transfers to others."
        ),
        size=(730, 530),
        splits={"train": 5_285, "val": 0, "test": 5_050},
        size_bytes=7_408_312_320,
        license="Research use only (SUN RGB-D terms)",
        homepage="https://rgbd.cs.princeton.edu/",
        registered_at=datetime(2026, 7, 2, 5, 48, 51, tzinfo=UTC),
        contract=DataContractOut(
            inputs="RGB uint8, 3x530x730 (resized from each sensor's resolution)",
            targets="Depth map float32, 530x730; 37-class label map uint8",
            units="metres",
            valid_range="0.001 to 10 m",
            missing_values="0 where the sensor returned no depth; label 0 is unlabelled",
            evaluation="Full frame, depth capped at 10 m; AbsRel, RMSE and delta1",
        ),
    ),
    _dataset(
        id="lab_scans_v1",
        name="Lab Indoor Scans",
        version="1.0",
        tasks=["monocular_depth"],
        modality="RGB-D (Intel RealSense D435i)",
        scenes="indoor (the lab's own building)",
        description=(
            "Corridors, offices and labs of the lab's building, recorded with a handheld Intel "
            "RealSense D435i: 3,214 aligned RGB-D frames from 18 rooms. Collected to test how "
            "models trained on NYU Depth V2 transfer to a new building and sensor."
        ),
        size=(848, 480),
        splits={"train": 2_571, "val": 321, "test": 322},
        size_bytes=4_402_341_478,
        license="Internal: lab members only",
        homepage=None,
        registered_at=datetime(2026, 9, 21, 9, 3, 40, tzinfo=UTC),
        contract=DataContractOut(
            inputs="RGB uint8, 3x480x848",
            targets="Depth map float32, 480x848 (converted from 16-bit millimetres)",
            units="metres",
            valid_range="0.1 to 6 m",
            missing_values="0 where stereo matching found no depth",
            evaluation="Full frame, depth capped at 6 m; AbsRel, RMSE and delta1",
        ),
    ),
)
