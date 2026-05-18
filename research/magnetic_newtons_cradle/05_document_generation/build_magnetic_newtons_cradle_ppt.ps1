$ErrorActionPreference = "Stop"

$Root = "C:\Users\66\Desktop\cupt\IYPT2026_Research\15_Magnetic_Newtons_cradle"
$Flow = Join-Path $Root "comsol_matlab_workflow"
$Out = Join-Path $Root "Magnetic_Newtons_Cradle_Theory_and_Simulation.pptx"
$PreviewDir = Join-Path $Root "ppt_preview"
New-Item -ItemType Directory -Force -Path $PreviewDir | Out-Null

$ppLayoutBlank = 12
$msoTextOrientationHorizontal = 1
$msoFalse = 0
$msoTrue = -1
$msoShapeRectangle = 1
$msoShapeRoundedRectangle = 5
$msoShapeOval = 9
$msoLine = 9

$ppt = New-Object -ComObject PowerPoint.Application
$ppt.Visible = $msoTrue
$pres = $ppt.Presentations.Add()
$pres.PageSetup.SlideWidth = 960
$pres.PageSetup.SlideHeight = 540

function RGB($r, $g, $b) {
    return [int]($r + 256 * $g + 65536 * $b)
}

$C = @{
    Ink = RGB 28 35 41
    Muted = RGB 88 96 105
    Paper = RGB 246 243 235
    Bone = RGB 235 228 213
    Red = RGB 190 62 51
    Blue = RGB 38 92 153
    Teal = RGB 35 125 116
    Gold = RGB 207 145 40
    Dark = RGB 23 29 35
    Green = RGB 56 138 91
    White = RGB 255 255 255
    Gray = RGB 210 211 208
}

function New-Slide {
    param([string]$Kicker, [string]$Title)
    $pres.Slides.Add($pres.Slides.Count + 1, $ppLayoutBlank) | Out-Null
    $slide = $pres.Slides.Item($pres.Slides.Count)
    $slide.FollowMasterBackground = $msoFalse
    $slide.Background.Fill.ForeColor.RGB = $C.Paper
    $bar = $slide.Shapes.AddShape($msoShapeRectangle, 0, 0, 960, 42)
    $bar.Fill.ForeColor.RGB = $C.Dark
    $bar.Line.Visible = $msoFalse
    if ($Kicker) {
        $null = Add-Text $slide $Kicker 34 12 220 18 9 $C.Gold $true
    }
    if ($Title) {
        $null = Add-Text $slide $Title 34 62 760 48 25 $C.Ink $true
    }
    $num = "{0:00}" -f $slide.SlideIndex
    $null = Add-Text $slide $num 890 13 40 16 9 $C.Gray $true
    return $slide
}

function Add-Text {
    param($Slide, [string]$Text, [double]$X, [double]$Y, [double]$W, [double]$H, [double]$Size, [int]$Color, [bool]$Bold = $false, [string]$Font = "Microsoft YaHei")
    if ($W -lt 1) { $W = 1 }
    if ($H -lt 1) { $H = 1 }
    try {
        $shape = $Slide.Shapes.AddTextbox($msoTextOrientationHorizontal, $X, $Y, $W, $H)
    } catch {
        Write-Host "Add-Text failed: X=$X Y=$Y W=$W H=$H Text=$Text"
        throw
    }
    $shape.TextFrame.TextRange.Text = $Text
    $shape.TextFrame.TextRange.Font.Name = $Font
    $shape.TextFrame.TextRange.Font.Size = $Size
    $shape.TextFrame.TextRange.Font.Color.RGB = $Color
    $shape.TextFrame.TextRange.Font.Bold = $(if ($Bold) { $msoTrue } else { $msoFalse })
    $shape.TextFrame.MarginLeft = 0
    $shape.TextFrame.MarginRight = 0
    $shape.TextFrame.MarginTop = 0
    $shape.TextFrame.MarginBottom = 0
    $null = $shape
}

function Add-Card {
    param($Slide, [double]$X, [double]$Y, [double]$W, [double]$H, [string]$Title, [string]$Body, [int]$Accent)
    $box = $Slide.Shapes.AddShape($msoShapeRoundedRectangle, $X, $Y, $W, $H)
    $box.Fill.ForeColor.RGB = $C.White
    $box.Line.ForeColor.RGB = $C.Gray
    $box.Line.Weight = 1
    $stripe = $Slide.Shapes.AddShape($msoShapeRectangle, $X, $Y, 6, $H)
    $stripe.Fill.ForeColor.RGB = $Accent
    $stripe.Line.Visible = $msoFalse
    Add-Text $Slide $Title ($X + 18) ($Y + 14) ($W - 30) 24 14 $Accent $true
    Add-Text $Slide $Body ($X + 18) ($Y + 44) ($W - 30) ($H - 54) 11 $C.Ink $false
}

function Add-Formula {
    param($Slide, [string]$Text, [double]$X, [double]$Y, [double]$W, [double]$H)
    $box = $Slide.Shapes.AddShape($msoShapeRoundedRectangle, $X, $Y, $W, $H)
    $box.Fill.ForeColor.RGB = RGB 255 253 248
    $box.Line.ForeColor.RGB = RGB 190 184 172
    $box.Line.Weight = 1.2
    Add-Text $Slide $Text ($X + 16) ($Y + 14) ($W - 28) ($H - 24) 14 $C.Ink $false "Cambria Math"
}

function Add-Image {
    param($Slide, [string]$Path, [double]$X, [double]$Y, [double]$W, [double]$H)
    if (Test-Path $Path) {
        $pic = $Slide.Shapes.AddPicture($Path, $msoFalse, $msoTrue, $X, $Y, $W, $H)
        $null = $pic
    } else {
        Add-Card $Slide $X $Y $W $H "Missing image" $Path $C.Red
    }
}

function Add-Line {
    param($Slide, [double]$X1, [double]$Y1, [double]$X2, [double]$Y2, [int]$Color, [double]$Weight = 2)
    $line = $Slide.Shapes.AddLine($X1, $Y1, $X2, $Y2)
    $line.Line.ForeColor.RGB = $Color
    $line.Line.Weight = $Weight
    $null = $line
}

function Add-BobSketch {
    param($Slide, [double]$X, [double]$Y, [double]$Scale)
    $piv = @(-2, -1, 0, 1, 2)
    $angles = @(-44.2, -20.1, 0, 20.1, 44.2)
    for ($i = 0; $i -lt 5; $i++) {
        $px = $X + ($piv[$i] * 62 * $Scale)
        $py = $Y
        $theta = $angles[$i] * [Math]::PI / 180
        $len = 145 * $Scale
        $bx = $px + [Math]::Sin($theta) * $len
        $by = $py + [Math]::Cos($theta) * $len
        Add-Line $Slide $px $py $bx $by $C.Ink 2
        $joint = $Slide.Shapes.AddShape($msoShapeOval, $px - 4, $py - 4, 8, 8)
        $joint.Fill.ForeColor.RGB = $C.Ink
        $joint.Line.Visible = $msoFalse
        $bob = $Slide.Shapes.AddShape($msoShapeOval, $bx - 18, $by - 18, 36, 36)
        $bob.Fill.ForeColor.RGB = $C.Blue
        $bob.Line.ForeColor.RGB = $C.Ink
        Add-Text $Slide ([string]($i + 1)) ($bx - 5) ($by - 7) 16 16 9 $C.White $true
    }
    Add-Line $Slide ($X - 155 * $Scale) $Y ($X + 155 * $Scale) $Y $C.Dark 4
}

# 1
$s = New-Slide "" ""
$s.Background.Fill.ForeColor.RGB = $C.Dark
Add-Text $s "Magnetic Newton’s Cradle" 46 68 780 55 34 $C.White $true
Add-Text $s "物理原理、真实磁场建模、频谱与混沌判据" 48 126 780 34 18 $C.Gold $false
Add-Text $s "研究对象：五摆磁力牛顿摆；参数来自实测 Tracker 与磁铁表面场" 50 436 760 24 13 $C.Gray $false
Add-BobSketch $s 690 190 1.05
Add-Text $s "4 cm 轴距 / 30 mm 直径 / 25 mm 厚 / 220 mT 表面场 / 70 g" 50 470 760 22 12 $C.Gray $false

# 2
$s = New-Slide "OBSERVATION" "实验现象不是普通牛顿摆：磁斥力改变了静止态与能量传递"
Add-Card $s 46 132 260 135 "普通牛顿摆" "接触碰撞主导；静止时摆球基本竖直排列；能量转移近似由动量和能量守恒解释。" $C.Blue
Add-Card $s 350 132 260 135 "磁力牛顿摆" "端部圆柱磁铁同极相对，未接触也存在强排斥；静止态会自动外扩。" $C.Red
Add-Card $s 654 132 260 135 "研究重点" "要同时处理：非均匀磁场、非线性耦合、多自由度动力学和初值敏感性。" $C.Teal
Add-BobSketch $s 480 332 1.0
Add-Text $s "关键转变：从 碰撞传递 变成 磁场耦合 + 重力回复 的多模态系统。" 92 500 780 26 16 $C.Ink $true

# 3
$s = New-Slide "PARAMETERS" "建模只允许使用可测量参数，而不是任意调力"
Add-Card $s 50 130 255 115 "几何" "轴固定点间距 d = 4 cm`n圆柱磁铁直径 3 cm`n厚度 2.5 cm" $C.Blue
Add-Card $s 352 130 255 115 "磁场" "表面中心场 B_surface = 220 mT`n由圆柱轴向场公式反推等效 Br = 0.513 T" $C.Red
Add-Card $s 654 130 255 115 "动力学" "单摆质量 m = 70 g`n阻尼取极小值`n左端释放角约 50°" $C.Teal
Add-Formula $s "Bᵣ = 2 B_surface · √(R² + L²) / L`nR = 0.015 m，L = 0.025 m，B_surface = 0.220 T`n所以：Bᵣ ≈ 0.513 T" 90 310 780 115
Add-Text $s "注意：N52 是材料等级；实验中表面实测场才是当前装置的有效约束。" 88 458 790 26 14 $C.Muted $false

# 4
$s = New-Slide "FIELD MODEL" "圆柱磁铁被近似为两个带等效磁荷的圆盘端面"
Add-Formula $s "轴线上磁场：`nB(x) = Bᵣ/2 · [(x+L/2)/√(R²+(x+L/2)²) − (x−L/2)/√(R²+(x−L/2)²)]`n`n端面中心：x = L/2`nB_surface = Bᵣ/2 · L/√(R²+L²)" 48 130 520 220
Add-Card $s 620 128 290 90 "为什么不用点偶极？" "近距离时磁铁尺寸与间隙同量级；点偶极会严重低估/高估近场结构。" $C.Red
Add-Card $s 620 242 290 90 "为什么不用指数力？" "F = K exp(-gap/lambda) 的 K 和 lambda 是拟合参数，不能解释磁铁几何变化。" $C.Blue
Add-Card $s 620 356 290 90 "本模型" "保留半径、厚度、表面场、横向偏移；磁场外延由圆盘积分自然给出。" $C.Teal

# 5
$s = New-Slide "FORCE TABLE" "磁力表：从二维间隙与侧向偏移映射到轴向/侧向力"
Add-Formula $s "面元磁荷：q = σₘ ΔA，且 σₘ = Bᵣ / μ₀`n`n两面元之间：`nΔF = μ₀/(4π) · q₁q₂/r³ · r⃗`n`n力表输出：轴向力 Fₓ 与侧向力 Fᵧ" 54 128 470 150
Add-Card $s 575 128 320 92 "输入" "gap：两端面表面间隙`noffset：圆盘中心侧向错位" $C.Blue
Add-Card $s 575 244 320 92 "输出" "force_axial_N：沿磁轴斥力`nforce_lateral_N：错位恢复/偏转分量" $C.Teal
Add-Card $s 575 360 320 92 "物理边界" "真实磁铁不允许零间隙重合；计算中保留最小表面间隙作为外壳/空气层。" $C.Red
Add-Text $s "这一步由 COMSOL 自带 Java 运行时生成力表，再由 MATLAB/Python 动力学脚本读取。" 60 486 820 22 13 $C.Muted $false

# 6
$s = New-Slide "STATIC EQUILIBRIUM" "静止角应由力矩平衡求出，而不是从照片手调"
Add-Formula $s "静态平衡条件：`nτᵢ(θ) = −m g Lᵢ sinθᵢ + Σⱼ (rᵢ × Fᵢⱼ)ᶻ = 0`n`n数值求解：让所有 |τᵢ| 同时最小" 56 126 490 105
Add-BobSketch $s 720 150 0.95
Add-Card $s 70 278 210 122 "1号 / 5号" "theta = ±44.23°`n外侧明显外撇" $C.Red
Add-Card $s 305 278 210 122 "2号 / 4号" "theta = ±20.14°`n中间邻近磁斥平衡" $C.Blue
Add-Card $s 540 278 210 122 "3号" "theta = 0°`n由左右对称性固定" $C.Teal
Add-Text $s "这与照片中的初始外扩形态一致；照片用于验证，不用于替代平衡方程。" 78 455 760 24 14 $C.Ink $true

# 7
$s = New-Slide "DYNAMICS" "释放后求解五自由度非线性摆方程"
Add-Formula $s "角加速度：θᵢ″ = τᵢ / (m Lᵢ²)`n`n总力矩：`nτᵢ = −m g Lᵢ sinθᵢ − cᵢ θᵢ′ + Σⱼ (rᵢ × Fᵢⱼ)ᶻ`n`n磁铁中心：xᵢ = pᵢ + Lᵢ sinθᵢ，yᵢ = −Lᵢ cosθᵢ" 50 125 560 185
Add-Card $s 650 122 250 84 "阻尼" "实验可振动数分钟，因此阻尼取极小；不靠大阻尼修形。" $C.Teal
Add-Card $s 650 226 250 84 "释放" "当前对比采用：从平衡态起，左端约 50° 释放。" $C.Red
Add-Card $s 650 330 250 84 "数值积分" "强磁近场导致刚性增强；用小步长 RK/ODE 方法求解。" $C.Blue

# 8
$s = New-Slide "PIPELINE" "模拟流程被拆成磁场、力表、动力学、实验对比四层"
$xs = @(70, 295, 520, 745)
$labels = @("1. 实测参数", "2. 有限圆柱力表", "3. 五摆动力学", "4. Tracker 对比")
$bodies = @("d, R, L, m, B_surface, release", "gap+offset -> Faxial+Flateral", "解静止角，再释放积分", "时间域、频谱、李指数")
$cols = @($C.Blue, $C.Red, $C.Teal, $C.Gold)
for ($i=0; $i -lt 4; $i++) {
    Add-Card $s $xs[$i] 180 170 120 $labels[$i] $bodies[$i] $cols[$i]
    if ($i -lt 3) { Add-Line $s ($xs[$i]+176) 240 ($xs[$i+1]-10) 240 $C.Muted 2 }
}
Add-Formula $s "建模原则：不人为缩放磁力。`n只修正可测量量：几何尺寸、有效表面场、摆长、释放角、阻尼。" 120 360 720 90

# 9
$s = New-Slide "TRACKER DATA" "实测轨迹显示低频整体模态和端部磁耦合峰并存"
Add-Image $s (Join-Path $Flow "tracker_vs_4cm_220mT_solved_eq_model_frequency.png") 55 122 850 330
Add-Card $s 70 470 250 48 "Tracker 主峰" "1.35-1.40 Hz" $C.Blue
Add-Card $s 350 470 250 48 "端部高频" "约 2.277 Hz" $C.Red
Add-Card $s 630 470 250 48 "模型端部" "约 2.25 Hz，吻合较好" $C.Teal

# 10
$s = New-Slide "RELEASE ANGLE" "50°释放增强非线性，但会降低低频主峰"
Add-Image $s (Join-Path $Flow "tracker_vs_4cm_220mT_release50deg_model_frequency.png") 55 120 850 318
Add-Card $s 82 462 240 54 "模型 50°" "主峰约 1.00-1.04 Hz 与 2.04 Hz" $C.Red
Add-Card $s 358 462 240 54 "实验" "主峰仍为 1.35-1.40 Hz 与 2.277 Hz" $C.Blue
Add-Card $s 634 462 240 54 "含义" "偏慢主要不是释放角太小，而是有效摆长/几何仍需修正。" $C.Teal

# 11
$s = New-Slide "CHAOS TEST" "混沌不能靠“看起来乱”，需要李雅普诺夫指数"
Add-Formula $s "两条几乎相同的轨迹：|δ(0)| = 10⁻⁷ rad`n`nBenettin 估计：`nλₘₐₓ = limₜ→∞ (1/t) Σₖ ln(|δₖ|/|δ₀|)`n`n判据：λₘₐₓ > 0 表示初值敏感" 54 122 470 210
Add-Image $s (Join-Path $Flow "realfield_4cm_220mT_solved_eq_release50deg_lyapunov.png") 560 120 340 250
Add-Card $s 80 390 230 76 "平衡附近释放" "lambda ≈ 0.077 s^-1，弱正值" $C.Blue
Add-Card $s 365 390 230 76 "50°释放" "lambda ≈ 0.211 s^-1，非线性更强" $C.Red
Add-Card $s 650 390 230 76 "解释" "大幅释放增强初值敏感性，但仍需用更多实测轨迹复核。" $C.Teal

# 12
$s = New-Slide "TAKEAWAYS" "当前模型已经解释端部磁耦合峰；下一步要校准有效摆长"
Add-Card $s 58 125 260 135 "已经成立" "由实测表面场反推 Br；有限圆柱磁场生成力表；静态平衡角自动求解；端部 2.25 Hz 峰接近 Tracker 2.277 Hz。" $C.Teal
Add-Card $s 350 125 260 135 "仍有偏差" "模型低频偏慢：1.0-1.25 Hz vs 实测 1.35-1.40 Hz；说明有效摆长或重心位置可能估计偏长。" $C.Red
Add-Card $s 642 125 260 135 "下一步" "用视频标定 pivot 到磁铁质心的真实长度；加入磁轴倾角/外壳间隙；用 5 个点完整 Tracker 数据反演参数。" $C.Blue
Add-Formula $s "最关键的实验修正：`n测量 L_eff = 悬点到磁铁质心的距离。`n若模型频率要从 1.2 Hz 提高到 1.38 Hz，通常意味着 L_eff 需要更短。" 96 330 760 105
Add-Text $s "结论：磁力牛顿摆是强非线性、多模态耦合系统；混沌可能出现，但必须用实测轨迹 + 李指数/Poincare 截面共同证明。" 88 480 810 36 14 $C.Ink $true

$pres.SaveAs($Out)
for ($i = 1; $i -le $pres.Slides.Count; $i++) {
    $path = Join-Path $PreviewDir ("slide_{0:00}.png" -f $i)
    $pres.Slides.Item($i).Export($path, "PNG", 1280, 720)
}
$pres.Close()
$ppt.Quit()

Write-Host "PPTX written to $Out"
Write-Host "Previews written to $PreviewDir"
