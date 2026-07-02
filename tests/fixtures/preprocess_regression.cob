       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPREP.
      *   PROCEDURE DIVISION in a comment must not start proc parsing.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WSAA-TEXT PIC X(40) VALUE 'HELLO '.
!!!!!! 9000-DISABLED SECTION.
      /   9100-COMMENTED SECTION.
       PROCEDURE DIVISION.
       1000-MAIN SECTION.
           MOVE 'ABC'
      -         'DEF' TO WSAA-TEXT.
           GO 1090-EXIT
       1090-EXIT.
           GOBACK.
