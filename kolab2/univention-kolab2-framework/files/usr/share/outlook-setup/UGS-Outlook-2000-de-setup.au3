; Univention UGS Outlook 2000 Setup
;  AutoIT(tm) script for configuration Outlook 2000 as UGS client
;
; Copyright 2006-2010 Univention GmbH
;
; http://www.univention.de/
;
; All rights reserved.
;
; The source code of this program is made available
; under the terms of the GNU Affero General Public License version 3
; (GNU AGPL V3) as published by the Free Software Foundation.
;
; Binary versions of this program provided by Univention to you as
; well as other copyrighted, protected or trademarked materials like
; Logos, graphics, fonts, specific documentations and configurations,
; cryptographic keys etc. are subject to a license agreement between
; you and Univention and not subject to the GNU AGPL V3.
;
; In the case you use this program under the terms of the GNU AGPL V3,
; the program is provided in the hope that it will be useful,
; but WITHOUT ANY WARRANTY; without even the implied warranty of
; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
; GNU Affero General Public License for more details.
;
; You should have received a copy of the GNU Affero General Public
; License with the Debian GNU/Linux or Univention distribution in file
; /usr/share/common-licenses/AGPL-3; if not, see
; <http://www.gnu.org/licenses/>.

;GuiDatei einbinden
#include <GuiConstants.au3>

;Starten der Installation OK? Abbrechen? Nach 10 Sek. automatisch OK
;$answer = MsgBox(65,"Installation","Die automatische Konfiguration von Outlook2000 als UGS-Client starten?",10)
;If $answer = 2 Then	
;	Exit
;EndIf

;oeffnen der Konfigurationsdatei
If $CmdLine[0] = 1 Then
	$file = FileOpen($CmdLine[1],0)
Else	
	$file = FileOpen("konfig2000.txt", 0)
EndIf
;Zeilenweises einlesen der Konfigurationsdatei.
$name1 = FileReadLine($file,1)   
$name2 = FileReadLine($file,2)
$mail1 = FileReadLine($file,3)
$mail2 = FileReadLine($file,4)
$serv = FileReadLine($file,5)
$pwrd = FileReadLine($file,6)
$line0 = FileReadLine($file,7)
$ldap = FileReadLine($file,8)
$checkhow = FileReadLine($file,9)

;Konfigurationsdatei schliessen
FileClose($file)

If $checkhow = ("1") Then 
	$checkCNx = ("-1")
	$checkCNy = ("1")
	$checkUNx = ("0")
	$checkUNy = ("4")
ElseIf $checkhow = ("2") Then
	$checkCNx = ("0")
	$checkCNy = ("4")
	$checkUNx = ("-1")
	$checkUNy = ("1")
ElseIf $checkhow = ("3") Then
	$checkCNx = ("-1")
	$checkCNy = ("1")
	$checkUNx = ("-1")
	$checkUNy = ("1")
Else
	$checkCNx = ("-1")
	$checkCNy = ("1")
	$checkUNx = ("-1")
	$checkUNy = ("1")
EndIf

$pflicht=("")
$ctrl = ("")
If $name1 <> ("") And $name2 <> ("") And $mail1 <> ("") And $mail2 <> ("") And $serv <> ("") And $pwrd <> ("") And $line0 <> ("") Then $ctrl = ("ok")

While $name1 = ("") or $name2 = ("") or $mail1 = ("") or $mail2 = ("") or $serv = ("") or $pwrd = ("") or $ctrl = ("")

;Hauptfenster erstellen
GUICreate("Outlook 2000 als UGS-Client mit Toltec Connector",405,440)
GUICtrlCreateLabel("Tool zur automatisierten Konfiguration ","15","15")
GUICtrlCreateLabel("von Outlook2000 als UGS-Client mit","15","30")
GUICtrlCreateLabel("Toltec-Connector ","15","45")
;Univention-Logo
GuiCtrlCreatePic("univention_logo.gif",240,10,150,50)
If Not FileExists("univention_logo.gif") Then
	GuiCtrlCreateLabel("" & @CRLF & "              UNIVENTION" & @CRLF & "        linux for your business", 240, 10, 150, 50)
	GuiCtrlSetBkColor(-1, 0xcc0033)
	GUICtrlSetColor(-1,0xffffff)
EndIf

GUICtrlCreateLabel("Auswahl:",15,83)

$checkCN = GUICtrlCreateCheckbox ("Outlook konfigurieren", 110, 80, 120, 20)
GuiCtrlSetState($checkCNx, $GUI_CHECKED)

$checkUN = GUICtrlCreateCheckbox ("Toltec konfigurieren", 270, 80, 120, 20)
GuiCtrlSetState($checkUNx, $GUI_CHECKED)

;Bezeichnung f�r folgende Eingabeaufforderung
GUICtrlCreateLabel("Name","15","123","60")
GUICtrlCreateLabel("*","47","123","","")
GUICtrlSetColor(-1,$pflicht)
;Eingabeaufforderung mit Default-Wert
$line01 = GUICtrlCreateInput($name1,"110","120","100","","")
If $name1 = ("") Then
	GUICtrlSetState(-1,$GUI_FOCUS)
EndIf	
GUICtrlCreateLabel("Vorname","218","123","80")
GUICtrlCreateLabel("*","260","123")
GUICtrlSetColor(-1,$pflicht)
$line02 = GUICtrlCreateInput($name2,"270","120","120","","")

GUICtrlCreateLabel("E-Mail ","15","163")
GUICtrlCreateLabel("*","47","163")
GUICtrlSetColor(-1,$pflicht)
$line03 = GUICtrlCreateInput($mail1,"110","160","120","","")

GUICtrlCreateLabel("@","234","163", "160")
$line04 = GUICtrlCreateInput($mail2,"250","160","140","","")

GUICtrlCreateLabel("Server","15","203","60")
GUICtrlCreateLabel("*","47","203")
GUICtrlSetColor(-1,$pflicht)
$line05 = GUICtrlCreateInput ($serv,"110","200","280","","")

GUICtrlCreateLabel("Passwort","15","243","80")
GUICtrlCreateLabel("*","60","240")
GUICtrlSetColor(-1,$pflicht)
$line06 = GUICtrlCreateInput("","110","240","280","",$ES_PASSWORD)
If $name1 <> ("") Then
	GUICtrlSetState(-1,$GUI_FOCUS)
EndIf
GUICtrlCreateLabel("Passwortkontrolle","15","283","120")
GUICtrlCreateLabel("*","100","280")
GUICtrlSetColor(-1,$pflicht)
$chkline = GUICtrlCreateInput("","110","280","280","",$ES_PASSWORD)

GUICtrlCreateLabel("LDAP-Suchbasis","15","323","120")
$line07 = GUICtrlCreateInput($ldap,"110","320","280","","")

GUICtrlCreateLabel("* Pflichtfelder","325","345")
GUICtrlSetColor(-1,$pflicht)
;Ok-Button erstellen
$ok = GUICtrlCreateButton ("OK","110","380","80")
;Abbrechen-Button erstellen
$cancel = GUICtrlCreateButton ("Abbrechen","230","380","80")

GUICtrlCreateLabel("� UNIVENTION GmbH, 2006, www.univention.de, Version 1.01","15","425","420")

;Das Fenster �ffnen
GUISetState()
	
While 1 

	$msg = GUIGetMsg()
	;warten auf welchen Button gedr�ckt wird
	if $msg = $Gui_Event_Close Then Exit
		
	if $msg = $cancel Then Exit
		
	if $msg = $ok Then ExitLoop
	
WEnd

;Die Benutzereingaben �bernehmen und abspeichern
$name1 = GUICtrlRead($line01)
$name2 = GUICtrlRead($line02)
$mail1 = GUICtrlRead($line03)
$mail2 = GUICtrlRead($line04)
$serv = GUICtrlRead($line05)
$pwrd = GUICtrlRead($line06)
$pwchk = GUICtrlRead($chkline)
$ldap = GUICtrlRead($line07)
$checkCNy = GUICtrlRead($checkCN)
$checkUNy = GUICtrlRead($checkUN)


If $pwchk <> $pwrd Then
	$ctrl = ("")
Else
	$ctrl = ("ok")
EndIf
	
$pflicht = ("0xff0000")
GUIDelete()

ContinueLoop
WEnd	

If $line0 = ("") Then
	$offic = ("C:\Programme\Microsoft Office\OFFICE\OUTLOOK.EXE")
	Else
		$offic = $line0
EndIf	
If Not FileExists($offic) Then
	MsgBox(64,"Fehler","Die Konfiguration wird abgebrochen, die Datei OUTLOOK.EXE konnte nicht gefunden werden.")
	Exit
EndIf

If $checkCNy = 1 Then
;outlook starten
run ($offic)
sleep (5000)
While 1
	If WinActive("Benutzername") Then
		WinActivate("Benutzername")
		Send ("{Enter}")
	EndIf
	
	If WinActive("Microsoft Outlook Setup-Assistent") Then
		ExitLoop	
	Endif
WEnd
	
WinWait("Microsoft Outlook Setup-Assistent")
WinActivate("Microsoft Outlook Setup-Assistent")
Send ("{DOWN}")
WinActivate("Microsoft Outlook Setup-Assistent")
Send ("{SPACE}")
WinActivate("Microsoft Outlook Setup-Assistent")
Send ("{ENTER}")
WinActivate("Microsoft Outlook Setup-Assistent")
Send ("{ENTER}")
;Die Benutzereingaben in die Dialogfelder eingeben
Winwait ("E-Mail-Kontoeigenschaften")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("UGS")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ($name1)
WinActivate("E-Mail-Kontoeigenschaften")
Send (" ")
WinActivate("E-Mail-Kontoeigenschaften")
Send ($name2)
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ($mail1)
WinActivate("E-Mail-Kontoeigenschaften")
Send ("@")
WinActivate("E-Mail-Kontoeigenschaften")
Send ($mail2)
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ($mail1)
WinActivate("E-Mail-Kontoeigenschaften")
Send ("@")
WinActivate("E-Mail-Kontoeigenschaften")
Send ($mail2)
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{RIGHT}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ($serv)
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ($serv)
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ($mail1)
WinActivate("E-Mail-Kontoeigenschaften")
Send ("@")
WinActivate("E-Mail-Kontoeigenschaften")
Send ($mail2)
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ($pwrd)
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{SPACE}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{RIGHT}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{RIGHT}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{SPACE}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{TAB}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{SPACE}")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("!b")
WinActivate("E-Mail-Kontoeigenschaften")
Send ("{ENTER}")
WinActivate("Microsoft Outlook Setup-Assistent")
Send ("{ENTER}")
WinActivate("Microsoft Outlook Setup-Assistent")
Send ("{ENTER}")
WinActivate("Microsoft Outlook Setup-Assistent")
Send ("{ENTER}")

Sleep(2000)
While 1
If WinExists("Microsoft Outlook") Then
		WinActivate("Microsoft Outlook")
		Send ("{ENTER}")
		ExitLoop
	else 
		ExitLoop	
	EndIf
WEnd
Sleep(2000)
While 1
	If WinExists("Internetsicherheitshinweis") Then
		WinActivate("Internetsicherheitshinweis")
		Send ("{ENTER}")
		ExitLoop
	Else
		ExitLoop
	EndIf
Wend
Sleep(2000)
While 1
If WinExists("Microsoft Outlook") Then
		WinActivate("Microsoft Outlook")
		Send ("{ENTER}")
		ExitLoop
	else 
		ExitLoop	
	EndIf
WEnd
Sleep(5000)
While 1
	If WinExists("Internetsicherheitshinweis") Then
		WinActivate("Internetsicherheitshinweis")
		Send ("{ENTER}")
		ExitLoop
	Else
		ExitLoop
	EndIf
Wend
Sleep(2000)
While 1
	If WinExists("Microsoft Outlook") Then
		WinActivate("Microsoft Outlook")
		Send ("{ENTER}")
		ExitLoop
	else 
		ExitLoop	
	EndIf
WEnd
Sleep(2000)
While 1
	If WinExists ("Willkommen bei Microsoft Outlook 2000! - Nachricht (HTML)") Then
		WinActivate ("Willkommen bei Microsoft Outlook 2000! - Nachricht (HTML)")
		Send("{ALTDOWN}")
		Send("{F4}")
		Send("{ALTUP}")
		ExitLoop
	Else
		ExitLoop
	EndIf
WEnd
Sleep(2000)
While 1
	If WinExists ("Microsoft Outlook-Hilfe") Then
		WinActivate ("Microsoft Outlook-Hilfe")
		Send("{ALTDOWN}")
		Send("{F4}")
		Send("{ALTUP}")
		ExitLoop
	Else
		ExitLoop
	EndIf
WEnd
Sleep(2000)
While 1
	If WinExists ("Willkommen bei Microsoft Outlook 2000! - Nachricht (HTML)") Then
		WinActivate ("Willkommen bei Microsoft Outlook 2000! - Nachricht (HTML)")
		Send("{ALTDOWN}")
		Send("{F4}")
		Send("{ALTUP}")
		ExitLoop
	Else
		ExitLoop
	EndIf
WEnd
Sleep(2000)
While 1
	If WinExists("Posteingang - Microsoft Outlook") Then
		WinActivate("Posteingang - Microsoft Outlook")
		Sleep(2000)
		If Not WinActive("Posteingang - Microsoft Outlook")Then
		Send("{ENTER}")
		ExitLoop
		Else
			ExitLoop
		EndIf
	Else 
		ExitLoop
	EndIf
WEnd
Sleep(2000)
While 1
	If WinExists ("Willkommen bei Microsoft Outlook 2000! - Nachricht (HTML)") Then
		WinActivate ("Willkommen bei Microsoft Outlook 2000! - Nachricht (HTML)")
		Send("{ALTDOWN}")
		Send("{F4}")
		Send("{ALTUP}")
		ExitLoop
	Else
		ExitLoop
	EndIf
WEnd
Sleep(5000)
While 1
	If WinExists ("Microsoft Outlook-Hilfe") Then
		WinActivate ("Microsoft Outlook-Hilfe")
		Send("{ALTDOWN}")
		Send("{F4}")
		Send("{ALTUP}")
		ExitLoop
	Else
		ExitLoop
	EndIf
WEnd
Sleep(3000)
While 1
	If WinExists ("Willkommen bei Microsoft Outlook 2000! - Nachricht (HTML)") Then
		WinActivate ("Willkommen bei Microsoft Outlook 2000! - Nachricht (HTML)")
		Send("{ALTDOWN}")
		Send("{F4}")
		Send("{ALTUP}")
		ExitLoop
	Else
		ExitLoop
	EndIf
WEnd
Sleep(2000)
While 1
	If WinExists ("Willkommen bei Microsoft Outlook 2000! - Nachricht (HTML)") Then
		WinActivate ("Willkommen bei Microsoft Outlook 2000! - Nachricht (HTML)")
		Send("{ALTDOWN}")
		Send("{F4}")
		Send("{ALTUP}")
		ExitLoop
	Else
		ExitLoop
	EndIf
WEnd
Sleep(2000)
WinWait ("Posteingang - Microsoft Outlook")
WinActivate("Posteingang - Microsoft Outlook")
Send ("{ALTDOWN}")
Send("?")
Send ("a")
Send("{ALTUP}")
Sleep (2000)
EndIf
While 1
	If WinExists("Internetsicherheitshinweis") Then
		WinActivate("Internetsicherheitshinweis")
		Send ("{ENTER}")
		ExitLoop
	Else
		ExitLoop
	EndIf
Wend
If $checkUNy = 1 Then
;Toltec einrichten. Achtung Lizenz muss Installiert sein!
If not WinExists("Posteingang - Microsoft Outlook") Then 
	Run ($offic)
EndIf
Sleep(3000)
While 1
If WinExists("Microsoft Outlook") Then
		WinActivate("Microsoft Outlook")
		Send ("{ENTER}")
		ExitLoop
	else 
		ExitLoop	
	EndIf
WEnd
While 1
	If WinExists("Internetsicherheitshinweis") Then
		WinActivate("Internetsicherheitshinweis")
		Send ("{ENTER}")
		ExitLoop
	Else
		ExitLoop
	EndIf
Wend
While 1
If WinExists("Microsoft Outlook") Then
		WinActivate("Microsoft Outlook")
		Send ("{ENTER}")
		ExitLoop
	else 
		ExitLoop	
	EndIf
WEnd
Winwait ("Posteingang - Microsoft Outlook")
WinActivate("Posteingang - Microsoft Outlook")
Send ("{ALT}")
Send ("x")
Send ("o")
WinWait ("Optionen")
WinActivate("Optionen")
send ("+{TAB}")
Send ("{RIGHT}")
Send ("{RIGHT}")
Send ("{RIGHT}")
Send ("{RIGHT}")
Send ("{RIGHT}")
Send ("{RIGHT}")
WinWait("Optionen","Toltec")
WinActivate("Optionen")
ControlClick ( "Optionen", "Toltec", "Button2") 
Sleep(2000)
Send ("!w")
Send ("!w")
Send ("!w")
Send($serv)
send ("{TAB}")
Send ($mail1)
Send ("@")
Send ($mail2)
send ("{TAB}")
Send ($pwrd)
ControlEnable ( "Toltec Connector", "Sicherheit", "Button4" )
ControlClick ( "Toltec Connector", "Sicherheit", "Button4" )
Send ("{ENTER}"
Sleep (20000)
While 1
	If WinExists("Internetsicherheitshinweis") Then
		WinActivate("Internetsicherheitshinweis")
		Send ("{ENTER}")
		ExitLoop
	Else
		ExitLoop
	EndIf
Wend

Send ("!w")
Send ("{ENTER}")
WinActivate("Optionen")
Send ("{Tab}")
Send ("{ENTER}")
EndIf
If $checkCNy = 1 Then
;free-busy listen einrichten
Send ("!x")
Send ("o")
WinActivate("Optionen")
send ("{TAB}")
send ("{TAB}")
send ("{TAB}")
WinActivate("Optionen")
Send ("{ENTER}")
WinActivate("Kalenderoptionen")
Send ("+{TAB}")
Send ("+{TAB}")
Send ("+{TAB}")
WinActivate("Kalenderoptionen")
Send ("{ENTER}")
WinActivate("Frei/Gebucht-Optionen")
send ("{TAB}")
send ("{TAB}")
send ("{TAB}")
WinActivate("Frei/Gebucht-Optionen")
Send ("http://")
WinActivate("Frei/Gebucht-Optionen")
Send ($serv)
WinActivate("Frei/Gebucht-Optionen")
Send ("/freebusy/%NAME%@%SERVER%.ifb")
WinActivate("Frei/Gebucht-Optionen")
Send ("{ENTER}")
send ("{TAB}")
WinActivate("Kalenderoptionen")
Send ("{ENTER}")
WinWait ("Optionen")
Send ("{ESC}")
Sleep (1000)
EndIf
;LDAP Konfiguration
If $ldap <> ("") Then
	WinActivate("Posteingang - Microsoft Outlook")
	Send("!x")
	Send("d")
	WinActivate("Dienste")
	Send("!h")
	WinActivate("Dienst zum Profil hinzuf�gen")
	Send("Microsoft LDAP-Verzeichnis")
	WinActivate("Dienst zum Profil hinzuf�gen")
	Send("{ENTER}")
	WinActivate("LDAP-Verzeichnisdienst")
	Send("UGS-LDAP-Verzeichnis")
	send ("{TAB}")
	WinActivate("LDAP-Verzeichnisdienst")
	Send($serv)
	send ("{TAB}")
	send ("{TAB}")
	send ("{TAB}")
	send ("{TAB}")
	send ("{TAB}")
	WinActivate("LDAP-Verzeichnisdienst")
	Send($ldap)
	WinActivate("LDAP-Verzeichnisdienst")
	Send("{ENTER}")
	Send("{ENTER}")
	Send("{ENTER}")
EndIf
Sleep (1000)
If $checkCNy <> ("1") And $checkUNy <> ("1") Then Exit
Winwait ("Posteingang - Microsoft Outlook")
WinActivate("Posteingang - Microsoft Outlook")
Send ("{ALT}")
Send("d")
Send("a")
Sleep (2000)
While 1
	If WinExists("Internetsicherheitshinweis") Then
		WinActivate("Internetsicherheitshinweis")
		Send ("{ENTER}")
		ExitLoop
	Else
		ExitLoop
	EndIf
Wend
;Kontroll-Nachricht
MsgBox(64, "Installation Info", "Outlook2000 wurde als UGS-Client konfiguriert")
