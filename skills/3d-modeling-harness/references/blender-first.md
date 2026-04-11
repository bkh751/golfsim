# Blender-first Baseline

이 문서는 `golfsim` 3D 자산 작업의 기본 툴체인 기준만 담는다.

## Toolchain
- authoring: Blender
- interchange: `glTF/GLB`
- browser preview: Three.js `GLTFLoader`
- future engine consumer: Godot glTF import

## Default stance
- Blender는 제작 기준 툴이다.
- 브라우저는 검증 기준 경로다.
- 둘 중 하나만으로 전체 파이프라인을 닫으려 하지 않는다.

## Export rules
- 가능하면 `glTF/GLB`를 기본 export로 사용한다.
- 렌더 메시와 충돌 메시를 분리할 수 있도록 object naming을 나눈다.
- 축, scale, pivot은 문서로 잠그기 전까지 임의 확장을 피한다.
- 엔진별 편의 설정은 공통 규격보다 우선하지 않는다.

## What to verify
- preview에서 mesh가 깨지지 않는지
- 기본 material 정보가 손실되지 않는지
- naming과 hierarchy가 계약 문서와 맞는지
- 카메라/physics 기준 좌표와 충돌하지 않는지
