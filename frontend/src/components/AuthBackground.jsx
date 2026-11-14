import { useRef, useMemo } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Float } from '@react-three/drei';
import useTokenColors from '../styles/tokenColors';

function ease(current, target, lambda, delta) {
  return current + (target - current) * (1 - Math.pow(lambda, delta * 60));
}

function AuraCore({ colors }) {
  const core = useRef();
  const ringA = useRef();
  const ringB = useRef();
  const group = useRef();

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    if (core.current) {
      core.current.rotation.y += delta * 0.18;
      core.current.rotation.z += delta * 0.04;
    }
    if (ringA.current) ringA.current.rotation.z += delta * 0.12;
    if (ringB.current) ringB.current.rotation.z -= delta * 0.08;
    if (group.current) {
      group.current.position.y = 0.6 + Math.sin(t * 0.3) * 0.15;
      group.current.rotation.y = t * 0.06;
      const s = 1 + Math.sin(t * 0.5) * 0.03;
      group.current.scale.setScalar(s);
    }
  });

  return (
    <group ref={group} position={[2.2, 0.6, -1]}>
      <mesh ref={core}>
        <icosahedronGeometry args={[1.1, 12]} />
        <meshStandardMaterial
          color={colors.accent}
          emissive={colors.accentHover}
          emissiveIntensity={0.3}
          metalness={0.4}
          roughness={0.2}
          transparent
          opacity={0.85}
        />
      </mesh>
      <mesh ref={ringA} rotation={[Math.PI / 2.15, 0.25, 0]}>
        <torusGeometry args={[2.0, 0.01, 10, 120]} />
        <meshStandardMaterial
          color={colors.accent}
          emissive={colors.accent}
          emissiveIntensity={0.6}
          transparent
          opacity={0.45}
        />
      </mesh>
      <mesh ref={ringB} rotation={[Math.PI / 1.72, -0.45, 0.35]}>
        <torusGeometry args={[2.5, 0.008, 10, 120]} />
        <meshStandardMaterial
          color={colors.accent}
          emissive={colors.accentHover}
          emissiveIntensity={0.5}
          transparent
          opacity={0.3}
        />
      </mesh>
      <OrbitNodes radius={2.0} count={4} tilt={[Math.PI / 2.15, 0.25, 0]} speed={0.14} size={0.08} color={colors.accent} />
      <OrbitNodes radius={2.5} count={5} tilt={[Math.PI / 1.72, -0.45, 0.35]} speed={-0.1} size={0.06} color={colors.accentHover} />
    </group>
  );
}

function OrbitNodes({ radius, count, tilt, speed, size, color }) {
  const group = useRef();
  const nodes = useMemo(
    () =>
      Array.from({ length: count }, (_, i) => {
        const angle = (i / count) * Math.PI * 2;
        return [Math.cos(angle) * radius, 0, Math.sin(angle) * radius];
      }),
    [radius, count]
  );
  useFrame((_, delta) => {
    if (group.current) group.current.rotation.y += delta * speed;
  });
  return (
    <group rotation={tilt}>
      <group ref={group}>
        {nodes.map((pos, i) => (
          <mesh key={i} position={pos}>
            <octahedronGeometry args={[size, 0]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.9} metalness={0.4} roughness={0.2} />
          </mesh>
        ))}
      </group>
    </group>
  );
}

function TechNode({ radius, detail, color, speed, position }) {
  const mesh = useRef();
  useFrame((state, delta) => {
    if (!mesh.current) return;
    mesh.current.rotation.y += delta * speed;
    mesh.current.rotation.x += delta * speed * 0.35;
    const s = 1 + Math.sin(state.clock.elapsedTime * speed * 2) * 0.04;
    mesh.current.scale.setScalar(s);
  });
  return (
    <Float speed={1.4} floatIntensity={0.7}>
      <mesh ref={mesh} position={position}>
        <icosahedronGeometry args={[radius, detail]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={0.22} />
      </mesh>
    </Float>
  );
}

function DustParticles({ count = 180, color }) {
  const points = useRef();
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 24;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 14;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 10 - 3;
    }
    return arr;
  }, [count]);
  useFrame((_, delta) => {
    if (points.current) {
      points.current.rotation.y += delta * 0.006;
      points.current.rotation.x += delta * 0.003;
    }
  });
  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={positions} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial size={0.02} color={color} transparent opacity={0.35} sizeAttenuation depthWrite={false} />
    </points>
  );
}

function GlassPanel({ position, rotation, size = [1.6, 1.0], depth = 0.3, color }) {
  const mesh = useRef();
  const baseRotation = useMemo(() => rotation, [rotation]);
  useFrame((state, delta) => {
    if (!mesh.current) return;
    const t = state.clock.elapsedTime;
    mesh.current.rotation.x = baseRotation[0] + Math.sin(t * 0.15) * depth * 0.3;
    mesh.current.rotation.y = baseRotation[1] + Math.cos(t * 0.12) * depth * 0.4;
    mesh.current.position.y = position[1] + Math.sin(t * 0.2) * depth * 0.5;
  });
  return (
    <mesh ref={mesh} position={position} rotation={baseRotation}>
      <planeGeometry args={[size[0], size[1]]} />
      <meshBasicMaterial color={color} transparent opacity={0.06} side="DoubleSide" depthWrite={false} />
    </mesh>
  );
}

export default function AuthBackground() {
  const colors = useTokenColors();
  return (
    <div className="auth-bg-canvas">
      <Canvas
        dpr={[1, 1.4]}
        camera={{ position: [0, 0.5, 7.5], fov: 42 }}
        gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
        style={{ background: 'transparent' }}
      >
        <ambientLight intensity={0.4} />
        <directionalLight position={[5, 6, 5]} intensity={0.9} />
        <pointLight position={[-5, -2, 3]} intensity={30} distance={20} decay={2} color={colors.accent} />
        <pointLight position={[6, 3, -3]} intensity={40} distance={24} decay={2} color={colors.accentHover} />

        <AuraCore colors={colors} />
        <DustParticles color={colors.textMuted} />
        <GlassPanel position={[-4.2, -0.8, -2.5]} rotation={[0.12, 0.4, 0.03]} size={[1.7, 1.0]} depth={0.25} color={colors.border} />
        <GlassPanel position={[4.5, -1.2, -3]} rotation={[-0.1, -0.4, -0.02]} size={[1.3, 0.85]} depth={0.35} color={colors.border} />
        <GlassPanel position={[-3.0, 2.0, -3.5]} rotation={[0.08, 0.6, 0.05]} size={[1.1, 0.7]} depth={0.2} color={colors.border} />
        <TechNode radius={0.35} detail={1} color={colors.accentHover} speed={0.15} position={[-3.8, 1.8, -2.5]} />
        <TechNode radius={0.25} detail={1} color={colors.accent} speed={-0.2} position={[3.9, 2.3, -3]} />
        <TechNode radius={0.2} detail={0} color={colors.accent} speed={0.25} position={[2.8, -2.2, -1.5]} />
      </Canvas>
    </div>
  );
}
