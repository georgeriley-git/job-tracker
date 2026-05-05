# setup_schedule.ps1
# Registers a Windows Task Scheduler job that runs the Nuclear Jobs Scraper
# twice a day (8:00 am and 1:00 pm), every day of the week.
#
# Run this ONCE from a normal (non-admin) PowerShell prompt:
#   cd "C:\Users\George Riley\job-tracker"
#   .\setup_schedule.ps1
#
# To remove the task later:
#   Unregister-ScheduledTask -TaskName "NuclearJobsScraper" -Confirm:$false

$TaskName  = "NuclearJobsScraper"
$BatchFile = "C:\Users\George Riley\job-tracker\run_scrape.bat"
$WorkDir   = "C:\Users\George Riley\job-tracker"
$TempXml   = "$env:TEMP\job_board_tracker_task.xml"

# Remove any existing task with this name before re-registering.
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Task XML: two CalendarTriggers — 08:00 and 13:00, Mon-Fri.
$xml = @'
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Scrapes nuclear job board portals at 8am and 1pm daily and refreshes dashboard.html</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-05-04T08:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <WeeksInterval>1</WeeksInterval>
        <DaysOfWeek>
          <Monday />
          <Tuesday />
          <Wednesday />
          <Thursday />
          <Friday />
          <Saturday />
          <Sunday />
        </DaysOfWeek>
      </ScheduleByWeek>
    </CalendarTrigger>
    <CalendarTrigger>
      <StartBoundary>2026-05-04T13:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <WeeksInterval>1</WeeksInterval>
        <DaysOfWeek>
          <Monday />
          <Tuesday />
          <Wednesday />
          <Thursday />
          <Friday />
          <Saturday />
          <Sunday />
        </DaysOfWeek>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>C:\Users\George Riley\job-tracker\run_scrape.bat</Command>
      <WorkingDirectory>C:\Users\George Riley\job-tracker</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
'@

# PowerShell 5.1 Out-File with -Encoding Unicode writes UTF-16 LE with BOM,
# which is exactly what schtasks.exe /Create /XML expects.
$xml | Out-File -FilePath $TempXml -Encoding Unicode

schtasks.exe /Create /XML "$TempXml" /TN "$TaskName" /F

Remove-Item $TempXml -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Task '$TaskName' registered successfully."
Write-Host ""
Write-Host "Schedule: Daily (Mon-Sun), 08:00 and 13:00 (2 runs per day)"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  Verify:    schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "  Run now:   schtasks /Run /TN $TaskName"
Write-Host "  Remove:    Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host ""
Write-Host "Dashboard: open  C:\Users\George Riley\job-tracker\dashboard.html  in your browser"
