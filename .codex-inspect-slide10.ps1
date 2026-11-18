$ErrorActionPreference = 'Stop'
$deckPath = 'D:\Users\sksam\Downloads\RAG_Project_Review_3.pptx'
$outDir = 'D:\Users\sksam\Documents\ChatGPT\RAG\.pptx-build\before'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$powerPoint = New-Object -ComObject PowerPoint.Application
$powerPoint.Visible = $true
$presentation = $powerPoint.Presentations.Open($deckPath, $false, $true, $false)
try {
    $slide = $presentation.Slides.Item(10)
    $slide.Export((Join-Path $outDir 'slide-10-before.png'), 'PNG', 1600, 900)
    "SLIDE_COUNT=$($presentation.Slides.Count)"
    "SLIDE_10_SHAPE_COUNT=$($slide.Shapes.Count)"
    for ($index = 1; $index -le $slide.Shapes.Count; $index++) {
        $shape = $slide.Shapes.Item($index)
        $text = ''
        if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
            $text = $shape.TextFrame.TextRange.Text -replace "`r|`n", ' '
        }
        "SHAPE=$index;TYPE=$($shape.Type);NAME=$($shape.Name);LEFT=$([math]::Round($shape.Left));TOP=$([math]::Round($shape.Top));WIDTH=$([math]::Round($shape.Width));HEIGHT=$([math]::Round($shape.Height));TEXT=$text"
    }
}
finally {
    $presentation.Close()
    $powerPoint.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($presentation)
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($powerPoint)
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
