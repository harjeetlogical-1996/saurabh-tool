/**
 * Client-side video compression for upload size reduction.
 *
 * Cloud Run's HTTP/1.1 frontend caps request bodies at 32 MB. Folder
 * uploads in the Voice Pair tool routinely exceed that when the user
 * drops in 4K reels, so we transparently re-encode each video below a
 * size threshold using the browser's <canvas>.captureStream() + the
 * MediaRecorder API. No external library — runs everywhere modern.
 *
 * Tradeoffs the caller should know about:
 *   - Decoding speed: ~realtime. A 30s clip takes ~30s to compress.
 *     (Not parallelisable in one tab — serialised per file.)
 *   - Format change: output is webm (VP9/Opus). The backend re-encodes
 *     to mp4 anyway, so this is transparent to the render.
 *   - Quality drop is visible compared to a 4K original, but invisible
 *     for typical 720p / shorts-style content.
 *   - iOS Safari doesn't expose MediaRecorder for video — we detect
 *     and skip compression there, falling back to the original upload
 *     (user gets the "folder too large" error in that case, but the
 *     image-pair path stays unaffected since images aren't compressed).
 *
 * On any failure we return the ORIGINAL File so the upload still
 * attempts — caller decides what to do with that.
 */

const COMPRESS_IF_LARGER_THAN = 5 * 1024 * 1024;       // 5 MB
const TARGET_BITRATE_BPS = 1_200_000;                  // ~1.2 Mbps (720p-ish quality)
const TARGET_MAX_HEIGHT = 720;

export async function compressVideoIfLarge(file: File): Promise<File> {
  // Skip small files — re-encoding a 2MB clip wastes the user's time.
  if (file.size <= COMPRESS_IF_LARGER_THAN) return file;

  // MediaRecorder is required for output; webm/vp9 is the most portable.
  // Some Safari versions advertise MediaRecorder but error on start —
  // we still try, and fall back if recording dies.
  if (typeof MediaRecorder === "undefined") return file;
  const mime = pickSupportedMime();
  if (!mime) return file;

  try {
    return await encodeViaCanvas(file, mime);
  } catch (e) {
    console.warn("[videoCompress] failed, using original:", e);
    return file;
  }
}

/** Probe MediaRecorder for the first webm codec it can actually record. */
function pickSupportedMime(): string | null {
  const candidates = [
    "video/webm;codecs=vp9,opus",
    "video/webm;codecs=vp8,opus",
    "video/webm",
  ];
  for (const m of candidates) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return null;
}

/**
 * Play the source video off-screen, paint each frame onto a <canvas>,
 * capture the canvas stream + a WebAudio stream of the source's audio
 * track, and record the combined stream into a webm Blob.
 *
 * This is the only client-side path that re-encodes WITHOUT loading a
 * 20MB WASM build of ffmpeg. The catch: it's "realtime" — we have to
 * actually play the video to its end.
 */
async function encodeViaCanvas(file: File, mime: string): Promise<File> {
  const url = URL.createObjectURL(file);
  const video = document.createElement("video");
  video.src = url;
  video.muted = false;          // need audio track for capture
  video.playsInline = true;
  video.crossOrigin = "anonymous";
  video.preload = "auto";

  await new Promise<void>((resolve, reject) => {
    video.onloadedmetadata = () => resolve();
    video.onerror = () => reject(new Error("Failed to load video metadata"));
  });

  const srcW = video.videoWidth;
  const srcH = video.videoHeight;
  if (!srcW || !srcH) {
    URL.revokeObjectURL(url);
    throw new Error("Video has no dimensions");
  }

  // Downscale so longest edge matches TARGET_MAX_HEIGHT (720p).
  let dstW = srcW;
  let dstH = srcH;
  const longest = Math.max(srcW, srcH);
  if (longest > TARGET_MAX_HEIGHT) {
    const scale = TARGET_MAX_HEIGHT / longest;
    dstW = Math.round(srcW * scale);
    dstH = Math.round(srcH * scale);
    // Even-align for codec safety (some encoders require multiples of 2).
    dstW -= dstW % 2;
    dstH -= dstH % 2;
  }

  const canvas = document.createElement("canvas");
  canvas.width = dstW;
  canvas.height = dstH;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    URL.revokeObjectURL(url);
    throw new Error("Canvas 2D context unavailable");
  }

  // Combine canvas video stream with the original audio track so the
  // re-encoded file still has speech. captureStream pulls the canvas;
  // the audio context routes the <video>'s audio out as a stream.
  const canvasStream = canvas.captureStream(30);
  const audioCtx = new AudioContext();
  const audioSource = audioCtx.createMediaElementSource(video);
  const audioDest = audioCtx.createMediaStreamDestination();
  audioSource.connect(audioDest);
  // Also connect to speakers so playback drives the realtime encoder,
  // but route through a 0-gain so the user doesn't hear it.
  const muteGain = audioCtx.createGain();
  muteGain.gain.value = 0;
  audioSource.connect(muteGain).connect(audioCtx.destination);

  const combinedStream = new MediaStream([
    ...canvasStream.getVideoTracks(),
    ...audioDest.stream.getAudioTracks(),
  ]);

  const recorder = new MediaRecorder(combinedStream, {
    mimeType: mime,
    videoBitsPerSecond: TARGET_BITRATE_BPS,
  });
  const chunks: BlobPart[] = [];
  recorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) chunks.push(e.data);
  };

  const recordingDone = new Promise<void>((resolve, reject) => {
    recorder.onstop = () => resolve();
    recorder.onerror = (e) => reject(e);
  });

  recorder.start(1000); // emit chunks every 1s so big videos don't OOM

  // Paint the video into the canvas as it plays.
  let rafId = 0;
  const paint = () => {
    if (video.paused || video.ended) return;
    ctx.drawImage(video, 0, 0, dstW, dstH);
    rafId = requestAnimationFrame(paint);
  };

  await video.play();
  paint();

  await new Promise<void>((resolve) => {
    video.onended = () => resolve();
  });
  cancelAnimationFrame(rafId);
  recorder.stop();
  await recordingDone;
  await audioCtx.close();
  URL.revokeObjectURL(url);

  const blob = new Blob(chunks, { type: mime });
  // Sanity check: if the "compressed" file is somehow BIGGER than the
  // original, return the original — happens occasionally on already-
  // optimised webm sources.
  if (blob.size >= file.size) return file;

  // Rename so the backend's extension check accepts it. Backend's
  // ALLOWED_VIDEO_EXTS includes .webm, so this is fine.
  const baseName = file.name.replace(/\.[^.]+$/, "");
  return new File([blob], `${baseName}.webm`, { type: mime });
}
