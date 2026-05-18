const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const ASSET_DIR = path.join(ROOT, "07_generated_assets", "formula_rendered");
const OUT_DIR = path.join(ROOT, "02_presentation");
const PPTX_PATH = path.join(OUT_DIR, "Magnetic_Newtons_Cradle_Theory_Formulas.pptx");

fs.mkdirSync(OUT_DIR, { recursive: true });

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "Codex";
pptx.subject = "Magnetic Newton's Cradle theory derivation";
pptx.title = "Magnetic Newton's Cradle Theory";
pptx.company = "CUPT/IYPT Research";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};
pptx.defineLayout({ name: "CUSTOM_WIDE", width: 13.333, height: 7.5 });
pptx.layout = "CUSTOM_WIDE";
pptx.margin = 0;

const C = {
  bg: "F7F4EC",
  ink: "17252C",
  muted: "66757B",
  teal: "1E5B67",
  teal2: "DCECEF",
  line: "B8C6C9",
  red: "B55245",
  gold: "C78B31",
  white: "FFFFFF",
};

function img(name) {
  return path.join(ASSET_DIR, `${name}.png`);
}

function addBase(slide, kicker, title, page) {
  slide.background = { color: C.bg };
  slide.addShape(pptx.ShapeType.line, { x: 0.55, y: 0.42, w: 12.25, h: 0, line: { color: C.line, width: 0.8 } });
  slide.addText(kicker, {
    x: 0.55, y: 0.18, w: 2.2, h: 0.24,
    fontFace: "Microsoft YaHei", fontSize: 8.8, bold: true,
    color: C.teal, margin: 0, breakLine: false,
    fit: "shrink",
    charSpace: 1.2,
  });
  slide.addText(title, {
    x: 0.55, y: 0.66, w: 8.9, h: 0.58,
    fontFace: "Microsoft YaHei", fontSize: 22, bold: true,
    color: C.ink, margin: 0,
    fit: "shrink",
  });
  slide.addText(String(page).padStart(2, "0"), {
    x: 12.2, y: 6.95, w: 0.6, h: 0.22,
    fontFace: "Arial", fontSize: 9, color: C.muted, align: "right", margin: 0,
  });
}

function addNote(slide, text, x, y, w, h) {
  slide.addText(text, {
    x, y, w, h,
    fontFace: "Microsoft YaHei", fontSize: 12,
    color: C.muted, breakLine: false,
    fit: "shrink",
    valign: "mid",
    margin: 0.03,
  });
}

function addFormula(slide, name, x, y, w, h, fill = C.white) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h,
    rectRadius: 0.06,
    fill: { color: fill, transparency: 0 },
    line: { color: C.line, width: 0.7 },
  });
  slide.addImage({ path: img(name), x: x + 0.18, y: y + 0.13, w: w - 0.36, h: h - 0.26, sizing: { type: "contain", x: x + 0.18, y: y + 0.13, w: w - 0.36, h: h - 0.26 } });
}

function addBullets(slide, bullets, x, y, w, h) {
  const text = bullets.map(b => ({ text: b, options: { bullet: { indent: 14 }, hanging: 4 } }));
  slide.addText(text, {
    x, y, w, h,
    fontFace: "Microsoft YaHei", fontSize: 13.2,
    color: C.ink,
    fit: "shrink",
    breakLine: false,
    margin: 0,
    paraSpaceAfterPt: 8,
  });
}

function addTag(slide, label, x, y, w, color = C.teal) {
  slide.addShape(pptx.ShapeType.rect, { x, y, w, h: 0.3, fill: { color }, line: { color, transparency: 100 } });
  slide.addText(label, { x: x + 0.08, y: y + 0.055, w: w - 0.16, h: 0.16, fontFace: "Microsoft YaHei", fontSize: 8.5, bold: true, color: C.white, align: "center", valign: "mid", margin: 0 });
}

// Slide 1
{
  const slide = pptx.addSlide();
  slide.background = { color: C.bg };
  slide.addText("磁力牛顿摆理论推导", { x: 0.7, y: 0.82, w: 8.2, h: 0.75, fontFace: "Microsoft YaHei", fontSize: 31, bold: true, color: C.ink, margin: 0 });
  slide.addText("基础定义 · 受力分析 · 磁力分解 · 总运动方程 · 模态解析", { x: 0.72, y: 1.7, w: 8.5, h: 0.33, fontFace: "Microsoft YaHei", fontSize: 14, color: C.muted, margin: 0 });
  slide.addShape(pptx.ShapeType.rect, { x: 0.72, y: 2.55, w: 3.1, h: 0.05, fill: { color: C.teal }, line: { transparency: 100 } });
  addFormula(slide, "f16_motion", 0.72, 3.02, 7.35, 1.14, C.white);
  addFormula(slide, "f22_eigen", 0.72, 4.45, 5.85, 0.92, C.white);
  slide.addShape(pptx.ShapeType.rect, { x: 9.55, y: 0, w: 3.78, h: 7.5, fill: { color: C.teal }, line: { transparency: 100 } });
  slide.addText("核心观点", { x: 10.0, y: 1.0, w: 2.6, h: 0.35, fontFace: "Microsoft YaHei", fontSize: 17, bold: true, color: C.white, margin: 0 });
  slide.addText("磁力牛顿摆不是普通单摆公式能描述的系统；频率来自重力刚度与磁耦合刚度共同决定的模态本征值。", { x: 10.0, y: 1.55, w: 2.65, h: 2.2, fontFace: "Microsoft YaHei", fontSize: 14, color: C.white, fit: "shrink", breakLine: false, margin: 0.03 });
  slide.addText("01", { x: 12.1, y: 6.92, w: 0.6, h: 0.25, fontFace: "Arial", fontSize: 9, color: "DDECEF", align: "right", margin: 0 });
}

// Slide 2
{
  const slide = pptx.addSlide();
  addBase(slide, "DEFINITIONS", "用一个摆角描述每个磁体的位置", 2);
  addFormula(slide, "f01_pivot", 0.7, 1.65, 5.15, 0.86);
  addFormula(slide, "f02_position", 0.7, 2.85, 6.2, 0.95);
  addFormula(slide, "f03_state", 0.7, 4.1, 6.45, 0.9);
  addBullets(slide, [
    "第 i 个磁体只有一个广义坐标 theta_i。",
    "x_i, y_i 由悬点位置、有效摆长和摆角共同决定。",
    "五个摆形成 10 维相空间。"
  ], 8.0, 1.7, 4.4, 2.2);
  addTag(slide, "N = 5", 8.0, 4.3, 1.1, C.red);
  addTag(slide, "L_eff 待校准", 9.35, 4.3, 1.65, C.gold);
  addTag(slide, "d = 4 cm", 11.25, 4.3, 1.1, C.teal);
}

// Slide 3
{
  const slide = pptx.addSlide();
  addBase(slide, "BASIC FORCES", "重力给回复力矩，阻尼给耗散", 3);
  addFormula(slide, "f04_gravity", 0.7, 1.65, 6.3, 0.95);
  addFormula(slide, "f05_damping", 0.7, 2.95, 4.55, 0.82);
  addBullets(slide, [
    "悬线拉力沿摆线方向，通过悬点，不进入角向力矩。",
    "重力项决定低频基础尺度，近似为 sqrt(g/L)。",
    "阻尼主要改变衰减速度和频谱峰宽。"
  ], 7.7, 1.7, 4.7, 2.45);
  addFormula(slide, "f23_damped", 7.15, 4.55, 5.45, 0.9, "FBFAF7");
}

// Slide 4
{
  const slide = pptx.addSlide();
  addBase(slide, "MAGNETIC GEOMETRY", "磁力由相对位置决定，而不是固定常数", 4);
  addFormula(slide, "f06_relative", 0.7, 1.55, 5.65, 0.82);
  addFormula(slide, "f07_gap", 0.7, 2.65, 5.9, 0.86);
  addFormula(slide, "f08_force_table", 0.7, 3.75, 6.9, 0.92);
  addBullets(slide, [
    "gap 描述两个圆柱磁体表面间隙。",
    "offset 描述两个中心的竖直错位。",
    "近距离大磁体不适合直接用点偶极模型。"
  ], 8.0, 1.55, 4.2, 2.2);
  addFormula(slide, "f10_dipole_scale", 8.0, 4.35, 4.3, 0.92, "FBFAF7");
}

// Slide 5
{
  const slide = pptx.addSlide();
  addBase(slide, "FORCE COMPONENTS", "磁力分解为水平主方向和竖直错位方向", 5);
  addFormula(slide, "f09_force_components", 0.7, 1.55, 7.1, 0.95);
  addFormula(slide, "f11_arm", 0.7, 2.88, 5.15, 0.82);
  addFormula(slide, "f12_magnetic_torque", 0.7, 4.02, 6.85, 0.95);
  addFormula(slide, "f13_magnetic_torque_expanded", 0.7, 5.34, 6.9, 0.92);
  addBullets(slide, [
    "F_x 主要由两个磁体的水平接近/远离产生。",
    "F_y 来自磁体中心的竖直错位。",
    "力矩由力臂和磁力叉乘得到。"
  ], 8.25, 1.7, 4.25, 2.1);
}

// Slide 6
{
  const slide = pptx.addSlide();
  addBase(slide, "EQUATION OF MOTION", "总力矩除以转动惯量得到角加速度", 6);
  addFormula(slide, "f14_total_torque", 0.7, 1.48, 8.1, 1.02);
  addFormula(slide, "f15_inertia", 0.7, 2.82, 3.6, 0.76);
  addFormula(slide, "f16_motion", 0.7, 3.9, 8.5, 1.05);
  addBullets(slide, [
    "完整方程含 sin、cos 和磁力表插值，是非线性耦合方程。",
    "低频主要受 g/L 控制。",
    "磁耦合项按 F/(mL) 进入角加速度。"
  ], 9.55, 1.6, 3.0, 2.8);
}

// Slide 7
{
  const slide = pptx.addSlide();
  addBase(slide, "STATE FORM", "数值积分使用一阶状态方程", 7);
  addFormula(slide, "f17_state_equations", 0.7, 1.55, 8.8, 1.15);
  addFormula(slide, "f18_equilibrium", 0.7, 3.2, 8.5, 1.05);
  addBullets(slide, [
    "先求静平衡，再从静平衡附近释放端部磁体。",
    "静平衡不是五个磁体竖直向下，而是磁力和重力力矩平衡后的展开构型。",
    "当前释放角约 50°，应明确是相对静平衡还是相对竖直方向。"
  ], 9.7, 1.55, 2.8, 3.0);
}

// Slide 8
{
  const slide = pptx.addSlide();
  addBase(slide, "LINEARIZATION", "频率来自静平衡附近的刚度矩阵", 8);
  addFormula(slide, "f19_linearization", 0.7, 1.6, 5.25, 0.85);
  addFormula(slide, "f20_matrix", 0.7, 2.76, 4.8, 0.82);
  addFormula(slide, "f21_stiffness", 0.7, 3.92, 5.4, 0.86);
  addFormula(slide, "f22_eigen", 0.7, 5.1, 6.0, 0.9);
  addBullets(slide, [
    "K 不是手设常数，而是总力矩对各摆角的导数。",
    "磁力改变 K 的非对角项，因此产生模态分裂。",
    "实验看到的是被初始释放条件激发出来的若干模态峰。"
  ], 7.6, 1.68, 4.8, 2.55);
}

// Slide 9
{
  const slide = pptx.addSlide();
  addBase(slide, "SPECTRUM", "模型解需要数值积分，再从时域转到频域", 9);
  addFormula(slide, "f24_fft", 0.7, 1.65, 5.4, 0.88);
  addFormula(slide, "f25_param", 0.7, 2.9, 6.6, 0.9);
  addBullets(slide, [
    "完整非线性方程没有简单闭式解析解。",
    "使用 Runge-Kutta 积分得到 theta_i(t)。",
    "对 theta_i(t) 做 FFT，与 Tracker 主峰比较。"
  ], 7.75, 1.65, 4.45, 2.25);
  addTag(slide, "Tracker 目标峰 1.38 Hz", 7.75, 4.45, 2.25, C.red);
  addTag(slide, "Tracker 目标峰 2.28 Hz", 10.25, 4.45, 2.25, C.teal);
}

// Slide 10
{
  const slide = pptx.addSlide();
  addBase(slide, "PARAMETER EFFECTS", "参数通过重力项、磁力项和阻尼项进入频率", 10);
  const rows = [
    ["L_i 增大", "g/L_i 下降", "低频峰降低"],
    ["d 增大", "磁力梯度减小", "磁耦合峰降低"],
    ["B 增大", "F_mag 约随 B² 增强", "磁耦合峰升高"],
    ["m 增大", "F/(mL) 减小", "磁耦合影响减弱"],
    ["c_i 增大", "耗散增强", "峰变宽、幅值降低"],
    ["theta_0 增大", "非线性增强", "频谱更复杂"],
  ];
  slide.addTable([
    [{ text: "参数变化", options: { bold: true } }, { text: "进入方程的位置", options: { bold: true } }, { text: "频率趋势", options: { bold: true } }],
    ...rows
  ], {
    x: 0.8, y: 1.55, w: 7.3, h: 4.7,
    border: { type: "solid", color: C.line, pt: 0.7 },
    color: C.ink,
    fontFace: "Microsoft YaHei",
    fontSize: 10.5,
    valign: "mid",
    margin: 0.08,
    fill: "FFFFFF",
    autoFit: false,
  });
  addFormula(slide, "f16_motion", 8.65, 1.7, 3.85, 1.15, "FBFAF7");
  addFormula(slide, "f22_eigen", 8.65, 3.22, 3.85, 0.95, "FBFAF7");
  addTextBoxSummary(slide);
}

function addTextBoxSummary(slide) {
  slide.addShape(pptx.ShapeType.rect, { x: 8.65, y: 4.75, w: 3.85, h: 1.14, fill: { color: C.teal }, line: { transparency: 100 } });
  slide.addText("一句话结论：L_eff 管摆本身有多快，d 和 B 管磁耦合有多强，释放角决定线性还是强非线性。", {
    x: 8.86, y: 4.93, w: 3.43, h: 0.78,
    fontFace: "Microsoft YaHei", fontSize: 12.5,
    color: C.white,
    fit: "shrink",
    breakLine: false,
    margin: 0,
  });
}

pptx.writeFile({ fileName: PPTX_PATH });
console.log(PPTX_PATH);
