"use client";

/**
 * Orb — a tiny 64x64 WebGL canvas that renders a sphere with a fragment shader.
 * The sphere is shaded with a violet to cyan gradient, a slow time uniform
 * breathes the colors, and a soft rim highlight gives the premium 3D look.
 *
 * The implementation is intentionally dependency-free (no Three.js, no
 * shader-lib) so the bundle stays small. Falls back to a static violet/cyan
 * gradient div on browsers without WebGL.
 */

import { useEffect, useRef } from "react";

const VERTEX_SRC = `
attribute vec2 aPosition;
varying vec2 vUv;
void main() {
  vUv = aPosition * 0.5 + 0.5;
  gl_Position = vec4(aPosition, 0.0, 1.0);
}
`;

const FRAGMENT_SRC = `
precision mediump float;
uniform float uTime;
uniform float uPixelRatio;
varying vec2 vUv;

void main() {
  vec2 p = (vUv - 0.5) * 2.0;
  float r = length(p);
  if (r > 1.0) discard;

  float z = sqrt(1.0 - r * r);
  vec3 n = normalize(vec3(p.x, p.y, z));

  float t = uTime * 0.6;
  vec3 light = normalize(vec3(cos(t) * 0.6, sin(t * 0.7) * 0.6, 1.0));

  float diffuse = max(dot(n, light), 0.0);
  float ambient = 0.42;

  vec3 viewDir = vec3(0.0, 0.0, 1.0);
  vec3 halfDir = normalize(light + viewDir);
  float specular = pow(max(dot(n, halfDir), 0.0), 28.0);

  vec3 violet = vec3(0.486, 0.361, 1.0);
  vec3 cyan = vec3(0.133, 0.827, 0.933);
  float band = 0.5 + 0.5 * sin(uTime * 0.4 + n.y * 1.8 + n.x * 0.6);
  vec3 base = mix(violet, cyan, band);

  float fresnel = pow(1.0 - z, 2.4);
  vec3 rimColor = mix(cyan, vec3(1.0), 0.35);

  vec3 color = base * (ambient + diffuse * 0.65) + rimColor * fresnel * 0.55;
  color += vec3(1.0) * specular * 0.55;

  float edge = smoothstep(0.96, 1.0, r);
  color *= (1.0 - edge * 0.6);

  gl_FragColor = vec4(color, 1.0);
}
`;

function compileShader(
  gl: WebGLRenderingContext,
  type: number,
  src: string,
): WebGLShader | null {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, src);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.error("Orb shader compile error", gl.getShaderInfoLog(shader));
    }
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

function linkProgram(
  gl: WebGLRenderingContext,
  vs: WebGLShader,
  fs: WebGLShader,
): WebGLProgram | null {
  const program = gl.createProgram();
  if (!program) return null;
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    gl.deleteProgram(program);
    return null;
  }
  return program;
}

export function Orb({ size = 64 }: { size?: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = (canvas.getContext("webgl", {
      antialias: true,
      alpha: true,
      premultipliedAlpha: false,
    }) as WebGLRenderingContext | null);
    if (!gl) return;

    const vs = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SRC);
    const fs = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SRC);
    if (!vs || !fs) return;
    const program = linkProgram(gl, vs, fs);
    if (!program) return;

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
      gl.STATIC_DRAW,
    );

    const aPosition = gl.getAttribLocation(program, "aPosition");
    const uTime = gl.getUniformLocation(program, "uTime");
    const uPixelRatio = gl.getUniformLocation(program, "uPixelRatio");
    gl.enableVertexAttribArray(aPosition);
    gl.vertexAttribPointer(aPosition, 2, gl.FLOAT, false, 0, 0);

    gl.useProgram(program);
    gl.uniform1f(uPixelRatio, window.devicePixelRatio || 1);

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    let raf = 0;
    const start = performance.now();
    const tick = () => {
      const t = (performance.now() - start) / 1000;
      gl.uniform1f(uTime, t);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      gl.deleteProgram(program);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      gl.deleteBuffer(buffer);
    };
  }, [size]);

  return (
    <div
      className="relative inline-flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <div
        aria-hidden
        className="absolute inset-0 -z-10 rounded-full opacity-70 blur-xl"
        style={{
          background:
            "radial-gradient(circle at 30% 30%, rgba(124,92,255,0.55), rgba(34,211,238,0.4) 60%, transparent 70%)",
        }}
      />
      <canvas
        ref={canvasRef}
        width={size}
        height={size}
        className="block rounded-full"
        style={{
          width: size,
          height: size,
          background:
            "radial-gradient(circle at 30% 30%, #7c5cff, #22d3ee 70%, transparent 90%)",
        }}
        aria-hidden
      />
    </div>
  );
}