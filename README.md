# CAD Watermarker

A local Python 3.11 web application for registering ownership marks in triangle meshes and checking a suspect model against an encrypted reference. The Flask interface accepts STL, OBJ and STEP, previews the mesh with Matplotlib, and exports binary STL or OBJ. Three sample models and a completed benchmark are included.

## Run on Windows

Extract the ZIP, open PowerShell in the folder containing `app.py`, and run

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Open **http://127.0.0.1:5000**. Keep the terminal open while using the app. On macOS or Linux, create the environment with `python3.11 -m venv .venv`, then use `.venv/bin/python` in the remaining commands. Installation downloads binary geometry libraries, including Open CASCADE and VTK through CadQuery. Use a 64-bit Python installation with compatible wheels.

## First round trip

1. Download **Box** in the sample panel, or choose an existing CAD file. The preview reports face and vertex counts.
2. In **Embed**, choose invisible mode, enter an owner name and optional identifiers, or select a PNG logo. Dark pixels represent the foreground. Transparency is composited over white. The logo is fitted within 32 × 32 pixels while preserving its aspect ratio.
3. Enter a password and select the output format. **Embed & register** writes a record only after the actual exported bytes pass verification. Download the marked model and save its 32-character registration ID.
4. In **Verify**, upload the exported model and enter the same password. The registration ID is filled from the downloaded filename or the browser's last registration. For a renamed suspect, enter its ID manually. A valid frame returns the owner details or bitmap extracted from the uploaded geometry.
5. Open **Evaluate** and enter the registration ID and password. Download the CSV and PNG chart. Evaluation always starts from the exact registered export.
6. For a visible mark, choose **Visible mark + verification**. Start with a broad, flat surface on a closed, consistently oriented solid. Enter a triangle index and inspect the highlighted face. Adjust the in-plane offsets, width, and relief depth. The UI expresses all four values as fractions of the input bounding-box diagonal. For text, the first line (owner name) is visible and the full metadata is embedded invisibly. Both marks survive in the same exported file.

**Registration storage.** Keep `records.sqlite3` from the project directory, the registration ID, and the password. The model by itself is insufficient for reference-assisted verification. To move installations, stop the app and copy the database to the new installation. Set `CAD_WATERMARK_DB` to choose a different database location. The browser remembers only the latest ID. Each record is independently sealed with AES-GCM. Registration is local and password-based. It does not establish an externally certified identity.

## Algorithm description for a manuscript

We implemented a reference-assisted spatial-domain watermark for triangulated CAD models. Input meshes are welded and cleaned of duplicate and degenerate triangles. Sparse models undergo uniform midpoint subdivision until sufficient distinct carriers exist. Centering, root-mean-square scaling and principal-component analysis provide a normalized coordinate frame. An edge-length-normalized umbrella operator ranks vertices by local geometric variation. A password-derived pseudorandom sequence samples distinct vertices from the upper half of this ranking. Flat regions can enter this set when many scores are tied.

The payload consists of UTF-8 ownership metadata or a packed binary logo. A synchronization identifier, payload length and CRC-32 precede the payload. PBKDF2-HMAC-SHA256 with a fresh 128-bit salt and 600,000 iterations derives a master key. HMAC-based domain separation produces keys for payload encryption, carrier selection and reference storage. AES-256-GCM encrypts and authenticates the frame with a random 96-bit nonce and 128-bit tag. Bits of the nonce, tag and ciphertext are embedded using three keyed, sign-modulated repetitions per bit. Each selected vertex moves along its unit normal by ±0.00004 times the bounding-box diagonal. The maximum invisible displacement is checked again after serialization against the 0.01% limit. Coordinates stay in the input coordinate system.

During verification, the recorded geometry provides a correspondence reference. The detector first considers the input pose, then searches the four orientation-preserving PCA sign choices for a similarity alignment. Near-coincident poses receive a least-squares rigid refinement. A nearest-neighbor search associates reference carriers with suspect vertices. Normal projections relative to the **unmarked** surface yield signed votes. Projections below 0.3 carrier amplitudes or offsets beyond 1.8 amplitudes are erased. The decoder sums the sign-corrected votes and authenticates the resulting frame with GCM, checks the header and CRC, and compares its ciphertext with the record. Tied votes count as erasures. This design permits experimental evaluation of partial ownership evidence when a damaged frame cannot be decrypted.

For visible marks, foreground runs of the raster silhouette form a planar cross-section, which is extruded in the selected face's tangent frame. Manifold Boolean union creates an emboss and Boolean difference creates a deboss. The implementation checks expected volume change, shell count, winding, watertightness and vertex fans before accepting the placement. An invisible frame is then added for verification. The invisible displacement limit applies to this final carrier layer. Visible relief has its own user-selected depth.

### Interpreting verification

| Verdict | Decision |
|---|---|
| ORIGINAL | GCM, CRC and reference frame match. Registered vertices match bijectively within 1% of a carrier amplitude, and all oriented faces match after index correspondence. Translation, proper rotation and uniform scale are accepted when registration succeeds. |
| MODIFIED | An authenticated frame survives a geometry or connectivity change, or the registered key opens the record and partial evidence reaches both experimental thresholds (85% decoded-bit agreement and 75% carrier agreement). |
| UNAUTHORIZED | The record or key fails, or the suspect supplies insufficient matching evidence. Severe processing of an authorized model can produce this result. |

**Tamper score** is 100 minus the percentage of correct individual carrier votes. Erasures count as errors. This measures damage to the watermark signal. A face-connectivity edit can therefore give MODIFIED with a 0% carrier mismatch. If GCM fails, the UI explicitly labels any displayed ownership information as coming from the encrypted registration record. Partial matching thresholds are heuristic and need independent false-positive calibration before forensic use.

## Evaluation and reproduction

Run these commands from the activated Python 3.11 environment

```bash
python -m pytest -q
python benchmark.py
```

The test suite exercises the three supplied families in both STL and OBJ, full clean recovery, wrong passwords, damaged frames, pose changes, visible emboss/deboss, PNG recovery, STEP tessellation, a vertex-pinched manifold counterexample and the application's registration-to-CSV workflow. The benchmark produces `evaluation/results.csv` and `evaluation/comparison.png`. Each registration uses fresh salts and nonces, so subsequent experimental scores can vary.

| Condition | Operation on a fresh copy of the exported mesh |
|---|---|
| Clean | Reload the serialized STL in the bundled benchmark, or the actual selected export in the UI |
| Gaussian noise | Independent per-axis noise with standard deviation 0.00001 × diagonal, seed 2027 |
| Rotation and scaling | Rotate 0.91 radians about (1, 2, 3), scale by 1.7 and translate by (0.2, −0.1, 0.4) |
| Crop | Remove 10% of faces from the high-x end according to centroid rank |
| Remesh | Quadric edge-collapse simplification to a target of half the original face count |
| Smooth | Two Laplacian iterations with λ = 0.25 and volume preservation disabled |

**Geometry metrics.** Exact symmetric Hausdorff distance between the two vertex sets is sensitive to inserted vertices, even on unchanged planar surfaces. The separate surface estimates query exact point-to-triangle distances in each direction using 4,096 area-sampled points plus up to 4,096 vertices per mesh. Their maximum estimates surface Hausdorff distance, and their root mean square estimates surface RMSE. All distances are in model units. The CSV includes input/output vertex counts, watertightness, vertex/edge manifoldness, winding consistency, and signed percentage volume change for closed oriented solids. Geometry comparison uses the input and clean export. Per-attack rows report extraction outcomes. These topology checks do not test printer-specific wall thickness, supports, or material tolerances.

**Measured scope.** In the included run, the box, cylinder and sphere each recovered 100% of bits after clean STL export and the specified similarity transform. Mesh simplification and smoothing prevented authenticated recovery on all three. The CSV records individual attack outcomes, including signal degradation when the authenticated frame survived. These are three synthetic models at one attack severity per condition. Broader robustness claims would require more diverse real CAD models, attack intensities, repeated keys and unrelated-model controls.

## Project map

| File | Responsibility |
|---|---|
| `app.py`, `templates/`, `static/` | Flask UI, previews, file export, evaluation and downloadable samples |
| `geometry.py` | Mesh cleanup, STEP tessellation, subdivision, PCA and export |
| `embed.py`, `extract.py` | Carrier selection, normal displacement, registration, decoding and verdicts |
| `crypto.py`, `records.py` | Password derivation, authenticated framing and encrypted SQLite records |
| `visible.py` | Planar raster relief and checked Boolean operations |
| `attacks.py`, `metrics.py`, `benchmark.py` | Attack conditions, geometric metrics and three-model comparison |
| `tests/`, `evaluation/` | Automated tests and measured results |

## Operating limits

Uploads are capped at 24 MiB per request, meshes at 300,000 triangles and payloads at 2,048 encoded bytes. Capacity depends on available carriers. Subdivision increases file size and triangle count. Shorten long payloads when the mesh cap would be exceeded. STEP files are tessellated with linear and angular tolerances of 0.1 in CadQuery's API. Exported files contain triangle geometry and omit parametric feature history, textures and assembly metadata.

Use OBJ or recenter a model if large absolute coordinates cause binary STL floating-point precision loss. Registration can fail on strongly cropped, noisy or highly symmetric geometry. Visible marks require enough supported planar area and sufficient local wall thickness. If a mark does not fit, reduce width/depth or change the face and in-plane offsets. Use a trusted local workstation for this prototype. It runs on the loopback interface and is designed for a single-user research workflow.
