import { useRef, useMemo, useEffect } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Float } from '@react-three/drei';
import { useMotionValueEvent } from 'framer-motion';
import useTokenColors from '../styles/tokenColors';

function ease(current, target, lambda, delta) {
  return current + (target - current) * (1 - Math.pow(lambda, delta * 60));
}

/* ─── Mouse tracking (shared across canvas children) ─── */
function MouseTracker({ mouseRef }) {
  const { viewport } = useThree();

  useEffect(() => {
    const onMove = (e) => {
      mouseRef.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouseRef.current.y = -(e.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener('mousemove', onMove, { passive: true });
    return () => window.removeEventListener('mousemove', onMove);
  }, [viewport, mouseRef]);

  return null;
}

/* ─── Glowing central sun / Morrow core ─── */
function Core({ progressRef, colors }) {
  const ref = useRef();
  const halo = useRef();

  useFrame((_, delta) => {
    const t = performance.now() * 0.001;
    const p = progressRef.current;
    if (ref.current) {
      ref.current.rotation.y += delta * 0.2;
      ref.current.rotation.x += delta * 0.08;
      const s = 1 + Math.sin(t * 1.4) * 0.04;
      ref.current.scale.setScalar(ease(ref.current.scale.x, s * (1 - p * 0.12), 0.92, delta));
    }
    if (halo.current) {
      halo.current.rotation.z += delta * 0.06;
      halo.current.scale.setScalar(1 + Math.sin(t * 0.9) * 0.03);
    }
  });

  return (
    <group>
      <mesh ref={ref}>
        <icosahedronGeometry args={[1.15, 8]} />
        <meshStandardMaterial
          color={colors.accent}
          emissive={colors.accentHover}
          emissiveIntensity={0.55}
          metalness={0.45}
          roughness={0.22}
          transparent
          opacity={0.92}
        />
      </mesh>
      <mesh ref={halo} rotation={[Math.PI / 2.1, 0.2, 0]}>
        <torusGeometry args={[1.9, 0.012, 12, 160]} />
        <meshStandardMaterial color={colors.accent} emissive={colors.accentHover} emissiveIntensity={0.6} transparent opacity={0.4} />
      </mesh>
    </group>
  );
}

/* ─── Single orbiting planet ─── */
function Planet({ radius, size, speed, color, ring, tilt, progressRef }) {
  const orbit = useRef();
  const mesh = useRef();
  const ringRef = useRef();

  useFrame((_, delta) => {
    const p = progressRef.current;
    if (orbit.current) orbit.current.rotation.y += delta * (speed + p * 0.55);
    if (mesh.current) {
      mesh.current.rotation.y += delta * 0.6;
      mesh.current.rotation.x += delta * 0.25;
    }
    if (ringRef.current) ringRef.current.rotation.x = Math.PI / 2.25;
  });

  return (
    <group ref={orbit} rotation={tilt}>
      <mesh ref={mesh} position={[radius, 0, 0]}>
        <sphereGeometry args={[size, 32, 32]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.32}
          metalness={0.35}
          roughness={0.45}
        />
      </mesh>
      {ring && (
        <mesh ref={ringRef} position={[radius, 0, 0]} rotation={[Math.PI / 2.4, 0, 0]}>
          <torusGeometry args={[size * 1.9, 0.014, 10, 80]} />
          <meshStandardMaterial
            color={color}
            emissive={color}
            emissiveIntensity={0.5}
            transparent
            opacity={0.5}
          />
        </mesh>
      )}
    </group>
  );
}

/* ─── Faint orbit guide-ring ─── */
function OrbitRing({ radius, color }) {
  const ref = useRef();
  useFrame((_, delta) => {
    if (ref.current) ref.current.rotation.z += delta * 0.04;
  });
  return (
    <mesh ref={ref} rotation={[Math.PI / 2, 0, 0]}>
      <torusGeometry args={[radius, 0.006, 8, 160]} />
      <meshBasicMaterial color={color} transparent opacity={0.12} />
    </mesh>
  );
}

/* ─── The solar system ─── */
// 	one names a colour token (see styles/tokenColors.js), so planets follow the palette.
const PLANETS = [
  { radius: 2.6, size: 0.30, speed: 0.26, tone: 'accent', ring: false, tilt: [0.28, 0, 0.18] },
  { radius: 3.7, size: 0.50, speed: 0.18, tone: 'accentHover', ring: true,  tilt: [-0.22, 0.1, -0.15] },
  { radius: 4.8, size: 0.24, speed: 0.34, tone: 'textMuted', ring: false, tilt: [0.15, 0, 0.3] },
  { radius: 5.9, size: 0.44, speed: 0.13, tone: 'accent', ring: true,  tilt: [-0.3, -0.12, 0.2] },
  { radius: 6.9, size: 0.20, speed: 0.42, tone: 'accentHover', ring: false, tilt: [0.2, 0, -0.25] },
];

function SolarSystem({ progressRef, mouseRef, colors }) {
  const group = useRef();

  useFrame((_, delta) => {
    const p = progressRef.current;
    const mx = mouseRef.current.x;
    const my = mouseRef.current.y;
    if (group.current) {
      group.current.rotation.y += delta * (0.05 + p * 0.28);
      group.current.rotation.x = ease(group.current.rotation.x, my * 0.16, 0.94, delta);
      group.current.position.x = ease(group.current.position.x, mx * 0.7, 0.94, delta);
      group.current.position.y = ease(group.current.position.y, my * 0.35 - p * 1.6, 0.94, delta);
    }
  });

  return (
    <group ref={group}>
      <Core progressRef={progressRef} colors={colors} />
      {PLANETS.map(({ tone, ...pl }, i) => (
        <Planet key={i} {...pl} color={colors[tone]} progressRef={progressRef} />
      ))}
      {PLANETS.map((pl, i) => (
        <OrbitRing key={'r' + i} radius={pl.radius} color={colors[pl.tone]} />
      ))}
    </group>
  );
}

/* ─── Subtle dust particles ─── */
function Dust({ count = 160, progressRef, color }) {
  const points = useRef();
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 28;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 18;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 14 - 3;
    }
    return arr;
  }, [count]);

  useFrame((_, delta) => {
    if (!points.current) return;
    const p = progressRef.current;
    points.current.position.y = ease(points.current.position.y, p * 2.6, 0.94, delta);
    points.current.rotation.y += delta * 0.006;
  });

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={positions} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial size={0.022} color={color} transparent opacity={0.32} sizeAttenuation depthWrite={false} />
    </points>
  );
}

/* ─── Glass panels drifting in background ─── */
function GlassPanel({ position, rotation, size = [1.7, 1.05], progressRef, depth = 0.35, color }) {
  const mesh = useRef();
  const baseRotation = useMemo(() => rotation, [rotation]);

  useFrame((_, delta) => {
    if (!mesh.current) return;
    const p = progressRef.current;
    mesh.current.rotation.x = baseRotation[0] + p * depth * 0.9;
    mesh.current.rotation.y = baseRotation[1] + p * depth * 1.4;
    mesh.current.position.y = position[1] + p * depth * -2.2;
  });

  return (
    <mesh ref={mesh} position={position} rotation={baseRotation}>
      <planeGeometry args={[size[0], size[1]]} />
      <meshBasicMaterial color={color} transparent opacity={0.05} side={2} depthWrite={false} />
    </mesh>
  );
}

/* ─── Camera dolly ─── */
function CameraRig({ progressRef }) {
  const { camera } = useThree();
  const target = useRef({ y: 0.35, z: 8 });

  useFrame((_, delta) => {
    const p = progressRef.current;
    target.current.y = 0.35 - p * 1.2;
    target.current.z = 8 + p * 2.4;
    camera.position.y = ease(camera.position.y, target.current.y, 0.93, delta);
    camera.position.z = ease(camera.position.z, target.current.z, 0.93, delta);
    camera.lookAt(0, 0, 0);
  });

  return null;
}

/* ─── Main exported component ─── */
export default function HeroScene({ scrollProgress }) {
  const progressRef = useRef(0);
  const mouseRef = useRef({ x: 0, y: 0 });
  const colors = useTokenColors();

  useMotionValueEvent(scrollProgress, 'change', (v) => {
    progressRef.current = v;
  });

  return (
    <div className="fixed inset-0 z-0 pointer-events-none">
      <Canvas
        dpr={[1, 1.5]}
        camera={{ position: [0, 0.35, 8], fov: 42 }}
        gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
        style={{ background: 'transparent' }}
      >
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 6, 5]} intensity={0.9} />
        <pointLight position={[-6, -2, 3]} intensity={32} distance={22} decay={2} color={colors.accent} />
        <pointLight position={[7, 3, -4]} intensity={46} distance={26} decay={2} color={colors.accentHover} />

        <MouseTracker mouseRef={mouseRef} />
        <CameraRig progressRef={progressRef} />
        <SolarSystem progressRef={progressRef} mouseRef={mouseRef} colors={colors} />
        <Dust progressRef={progressRef} color={colors.textMuted} />

        <GlassPanel position={[-4.6, -0.6, -2]} rotation={[0.15, 0.5, 0.03]} size={[1.9, 1.15]} progressRef={progressRef} depth={0.3} color={colors.border} />
        <GlassPanel position={[4.9, -1.4, -3]} rotation={[-0.1, -0.45, -0.02]} size={[1.5, 0.95]} progressRef={progressRef} depth={0.42} color={colors.border} />
      </Canvas>
    </div>
  );
}
