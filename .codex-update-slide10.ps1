$ErrorActionPreference = 'Stop'

$sourceDeck = 'D:\Users\sksam\Downloads\RAG_Project_Review_3.pptx'
$outputDeck = 'D:\Users\sksam\Downloads\RAG_Project_Review_3_AKYRA.pptx'
$buildDir = 'D:\Users\sksam\Documents\ChatGPT\RAG\.pptx-build'
$ingestionShot = 'C:\Users\sksam\AppData\Local\Temp\codex-clipboard-cbe0cf68-9217-4290-957e-4ca866115bf3.png'
$answerShot = 'C:\Users\sksam\AppData\Local\Temp\codex-clipboard-1eaf68a4-f953-4252-b9be-633e3a5d2b4f.png'

function New-CroppedScreenshot([string]$inputPath, [string]$outputPath, [double]$targetRatio) {
    Add-Type -AssemblyName System.Drawing
    $image = [System.Drawing.Image]::FromFile($inputPath)
    try {
        $sourceRatio = $image.Width / $image.Height
        if ($sourceRatio -gt $targetRatio) {
            $cropHeight = $image.Height
            $cropWidth = [math]::Round($cropHeight * $targetRatio)
            $cropX = [math]::Round(($image.Width - $cropWidth) / 2)
            $cropY = 0
        }
        else {
            $cropWidth = $image.Width
            $cropHeight = [math]::Round($cropWidth / $targetRatio)
            $cropX = 0
            $cropY = [math]::Round(($image.Height - $cropHeight) / 2)
        }
        $bitmap = New-Object System.Drawing.Bitmap $cropWidth, $cropHeight
        try {
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                $graphics.DrawImage($image, (New-Object System.Drawing.Rectangle 0, 0, $cropWidth, $cropHeight), $cropX, $cropY, $cropWidth, $cropHeight, [System.Drawing.GraphicsUnit]::Pixel)
            }
            finally { $graphics.Dispose() }
            $bitmap.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)
        }
        finally { $bitmap.Dispose() }
    }
    finally { $image.Dispose() }
}

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$targetRatio = 432 / 259
$croppedIngestion = Join-Path $buildDir 'akyra-ingestion-cropped.png'
$croppedAnswer = Join-Path $buildDir 'akyra-answer-cropped.png'
New-CroppedScreenshot $ingestionShot $croppedIngestion $targetRatio
New-CroppedScreenshot $answerShot $croppedAnswer $targetRatio

Copy-Item -LiteralPath $sourceDeck -Destination $outputDeck -Force
$powerPoint = New-Object -ComObject PowerPoint.Application
$powerPoint.Visible = $true
$presentation = $powerPoint.Presentations.Open($outputDeck, $false, $false, $false)
try {
    $slide = $presentation.Slides.Item(10)

    $title = $slide.Shapes.Item(1)
    $title.TextFrame.TextRange.Text = 'Live Demo: AKYRA Ingestion & Answering'

    $leftImage = $slide.Shapes.Item(2)
    $left = $leftImage.Left; $top = $leftImage.Top; $width = $leftImage.Width; $height = $leftImage.Height
    $leftImage.Delete()
    $newLeftImage = $slide.Shapes.AddPicture($croppedIngestion, $false, $true, $left, $top, $width, $height)
    $newLeftImage.Name = 'AKYRA Ingestion Screenshot'

    $rightImage = $slide.Shapes.Item(2)
    $left = $rightImage.Left; $top = $rightImage.Top; $width = $rightImage.Width; $height = $rightImage.Height
    $rightImage.Delete()
    $newRightImage = $slide.Shapes.AddPicture($croppedAnswer, $false, $true, $left, $top, $width, $height)
    $newRightImage.Name = 'AKYRA Answer Screenshot'

    # After deleting and adding images, locate the caption and flow text by their current content.
    for ($index = 1; $index -le $slide.Shapes.Count; $index++) {
        $shape = $slide.Shapes.Item($index)
        if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
            $current = $shape.TextFrame.TextRange.Text
            if ($current -like 'Query interface:*') {
                $shape.TextFrame.TextRange.Text = 'Index public websites or upload documents'
            }
            elseif ($current -like 'Ingestion console:*') {
                $shape.TextFrame.TextRange.Text = 'Ask questions and review source-backed answers'
            }
            elseif ($current -like 'Demo flow:*') {
                $shape.TextFrame.TextRange.Text = 'Demo flow: add a website or file, ask a question, then review the answer and source trace.'
            }
        }
    }

    $presentation.Save()
    $slide.Export((Join-Path $buildDir 'slide-10-after.png'), 'PNG', 1600, 900)
    "SLIDE_COUNT=$($presentation.Slides.Count)"
    "SLIDE_10_SHAPE_COUNT=$($slide.Shapes.Count)"
}
finally {
    $presentation.Close()
    $powerPoint.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($presentation)
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($powerPoint)
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
