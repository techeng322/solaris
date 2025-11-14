1. You need to develop a program to calculate solar exposure time. What key Russian standards and regulations must it comply with?

- SanPiN 1.2.3685-21 (hygienic standards and safety requirements)
- GOST R 57795-2017 (methods for calculating the duration of insolation) (as amended in 2021-2022)
- SP 52.13330.2016 (requirements for natural and artificial lighting)
- SP 367.1325800.2017 (design standards for residential and public buildings)
- It is necessary to use the calculation formula KEO 3.11 from Amendment No. 1 to SP 367.1325800.2017

2. Based on the analysis of existing programs ( Base , Solaris , Altec Insolations ), what are the main problems you need to solve?

– Accuracy issues: Altec overstates the values by a few seconds (1:29 vs. the required 1:30)
– User interface: Complex interfaces that require a long learning curve
– Integration issues: Problems exporting to REVIT and incorrect results
– Reporting issues: Overlapping calculation points, chaotic sequence of plans
– Ability to work offline: The need to work without an internet connection
– Window recognition: Automatic detection of window types and input of parameters
– Loggia calculations: Management of rooms behind loggias without external windows

3. How would you design a system architecture to address these problems?

Answer:
– Hybrid architecture: Desktop application with optional cloud synchronization
BIM Integration : Robust REVIT / AutoCAD plugin with validation
– Modular design: Separate calculation, user interface and reporting modules
– Database: Local SQLite with cloud backup for storing models
API Integration : RESTful API for billing services
– Offline operation: Basic functions work without the Internet

4. What key features should your program include?

Answer:
– Accurate calculations: Accurate determination of the duration of insolation (up to seconds)
KEO calculations : Side lighting according to formula 3.11
BIM integration : Convenient import/export from REVIT / AutoCAD
– Room classification: Automatic detection of room type
– Window recognition: Automatic detection of window parameters (thickness, light transmittance)
– Loggia support: Calculation of rooms behind loggias
– Report Creation: Professional reports with correct formatting
– Support for multi-story buildings: Working with complex building structures

5. How would you improve the usability of the program compared to existing solutions?

Answer:
- Intuitive interface: step-by-step wizard for new users
- Context-sensitive help: built-in tutorials and tips
- Template system: preset parameters for common building types
- Visual feedback: real-time preview of calculations
- Error prevention: input validation and warnings
- Gradual disclosure: Advanced features are hidden until needed

6. What technologies would you use for development?

Answer:
- Interface: C # WPF or . NET MAUI for cross-platform desktop
- Backend: .NET Core Web API for billing services
- Database: SQLite for local storage, PostgreSQL for the cloud
- Integration with BIM : Autodesk Forge API for integration with REVIT
- Graphics: DirectX / OpenGL for 3D visualization
- Reporting: Crystal Reports or similar for professional output

7. How will you ensure accuracy and compliance with standards?

– Validation tests: comparison of results with manual calculations.
– Compliance with standards: regular inspections for compliance with Russian building codes and regulations.
– User testing: beta testing with architects and engineers.
– Documentation: detailed user manuals and technical documentation.
– Support: ongoing maintenance and updating in accordance with changes in regulations.

8. How is your solution better than existing programs?

Answer:
– Accuracy: accurate calculations without inflated costs.
– Ease of use: intuitive interface that requires minimal training.
– Reliability: reliable integration with BIM without export problems.
– Flexibility: work offline and online.
– Completeness: support for all types of buildings, including loggias.
– Professional results: clear, structured reports and diagrams.

9. What are the main risks and how would you minimize them?

– Technical risks: Complexity of BIM integration → Use of proven APIs and extensive testing
– Regulatory risks: Changing standards → Modular design for easy upgrades
– User adoption: Learning curve → Comprehensive training and support
– Performance: Large building models → Optimized algorithms and caching
– Compatibility: Various CAD versions → Support for various formats

10. What specific problems or limitations have you encountered while using your current software?

- 1.Base is an old program. It calculates based on the entered data, calculating each room separately. It's like a calculator, but only for insolation and KEO. All diagrams must be drawn manually in AutoCAD . The program doesn't output data; everything must be assembled manually.

2. Solaris is an advanced program, but a bit complex. The program allows you to create a scene, set calculation points, and based on the scene and the specified parameters, it generates a calculation with graphical justification and additional diagrams. There's a plugin that allows you to export BIM models.
Cons:
* The interface and construction system are quite complex; without additional training videos, there is a risk of hitting the wrong button.
* Quite often a problem arises when exporting a model from Revit , which is why it is calculated incorrectly
* When downloading the report in the graphical section, the calculation points overlap each other, making it difficult to read. Plan captions periodically migrate to another sheet. The plan sequence is quite chaotic.

3. DIALux is a program designed for calculating the cost of equity. It's a European program in which calculations are based on a model. A model from Revit can also be imported . Disadvantages:
- Only KEO counts
Because the programs are European-style, the values are entered in a very strange way. For example, the calculated safety factor. In Russia, if the standard for lamps is 1.4, then in Dialux it's exactly the opposite: 0.71.
- When importing from Revit, the model becomes very heavy, which leads to system errors.

4. Altec Insolations 
A browser-based program, all models are stored in your personal account, so you can return to editing them if needed. It's very convenient. A plugin is installed on the Revit model. Preparing the model for export is quite simple: arrange the rooms by floors. To calculate the areas, draw the floor and enter Area 1, Area 2 in the parameters. When exporting, you select the buildings you want to calculate and immediately name them: Building 1. And that's it – a ready-to-calculate model in the program. The interface is intuitive, and if something isn't clear, there are step-by-step instructions right there. When exporting, you can immediately create a fully formatted explanatory note with stamps and signatures. Beautiful diagrams.
Cons:
"Their calculations are slightly overstated, and for apartments where insolation is measured in seconds, this is very important. Because if a consistent insolation of 1:30 is needed, and they set it to 1:29, then that apartment is highlighted in red throughout the report, although it should appear. The permissible error of the method for determining insolation duration using insolation graphs and solar maps is no more than ±10 minutes."

Regarding the layout of plans for both KEO and insolation. When exporting, you can select the plans you want to use for the calculation. You can also set the scale you want to see them at. This is convenient because, for example, if the sheet is A3 and the plan is small, you can set the scale to 1:50. And everything looks great, everything is visible. BUT, if you have several sections in the file and you set the scale you need, everything is cropped in a strange way and the calculation points are not shown. It's a real mess.
- It doesn't work without the internet. And sometimes it's a shame.
- Window types aren't recognized when exporting. And if there are multiple windows, you need to specify parameters for each one, down to the glass thickness and its transmittance.
"It doesn't consider the illumination of rooms through loggias. And everything seems to be there, even the rooms. But it usually doesn't perceive the room from behind the loggia because it doesn't have an outside window."
- It also does not take into account the influence of a window on a room if there is a nominal room without a partition in front of it.

11. Are there any additional features or capabilities you would like to see in the new software that are not available in existing programs?

- Of all the programs, I would like to see functionality closer to Altec Insolations . However, the ability to edit the text portion of the report and fill in stamps is missing. 


12. How would you prioritize the following features:

Answers
– Calculation of the duration of insolation based on established standards.
– Illuminance calculation ( ILC ) to meet regulatory requirements.
– KEO for calculating side lighting.
– Export data to other formats or programs (e.g. BIM models, CAD).

13. What specific requirements must be met to ensure compliance with the following standards?

- SanPiN 1.2.3685-21
- GOST R 57795-2017
- SP 52.13330.2016
- SP 367.1325800.2017

14. How are they criticized?
What is the accuracy of determining the insolation time, especially for rooms with a specific insolation duration (e.g. 1:30)?

- According to GOST R 57795-2017 Buildings and structures. Methods for calculating the duration of insolation (with Amendments No. 1, 2) 5.8 The permissible error of the method for determining the duration of insolation using insolation graphs and solar maps is no more than ±10 min

15. Are there any specific regions or building types for which the program should be optimized (e.g. residential, commercial)?
An insolation graph and solar map developed for a specific geographic latitude can be used to calculate the duration of insolation within ±1.0°

Insolation graphs for calculating the duration of insolation of rooms and territories are a combination of hourly radial lines and shadow path lines on the day of the beginning (end) of the insolation period, as shown in Figure 1.
Solar maps are a horizontal plane in the form of a circle with the sun's trajectory from sunrise to sunset at a certain point in time plotted on it, depending on the azimuth and altitude of the sun.

The calculation of the duration of insolation of premises for a certain period is carried out on the day of the beginning of the period or the day of its end for:
- northern zone (north of 58° N ) - April 22 or August 22;
- central zone (58° N - 48° N ) - April 22 or August 22;
- southern zone (south of 48° N ) - February 22 or October 22.

In general, there is a calculation methodology, "GOST R 57795-2017 Buildings and Structures. Methods for Calculating Insolation Duration," which describes the requirements for calculating insolation.

SanPiN 1.2.3685-21 (requirements for natural and artificial lighting) specifies the standard values for insolation and KEO.
- Insolation should be for residential buildings:

Standardized premises	Geographical latitude of the area	Duration 
of insolation, not less than	Calendar period
1. At least in one room of 1-3-room apartments;	Northern zone 
(north of 58° N )	2.5 hours	from April 22 
to August 22

2. At least 2 rooms of 4 and	Central zone 
(58° N - 48° N )	2 hours	
more than 60% of residential rooms in dormitory buildings; 

3. At least 60% of residential rooms in dormitory buildings	Southern zone 
(south of 48° N )	1.5 hours	from February 22 
to October 22
1. In 2- and 3-room apartments, where at least 2 rooms are insolated ;	Northern zone 
(north of 58° N )	2 hours	from April 22 
to August 22

2. In multi-room apartments	Central zone 
(58° N - 48° N )	1.5 hours	
(4 or more rooms), where at least 3 rooms 

are insolated ; 3. During the reconstruction of residential buildings located in the central, historical zones of cities, as defined by their general development plans	Southern zone 
(south of 48° N )	1.5 hours	from February 22 
to October 22


- Insolation should be for public buildings:

Standardized premises	Geographical 
latitude of the area	Duration 
of insolation, not less than	Calendar period
Pre-school educational organizations - group, play;	Northern zone 
(north of 58° N )	2.5 hours	from April 22 
to August 22

Educational organizations	Central zone 
(58° N - 48° N )	2 hours	
(general education, additional and vocational education, boarding schools, orphanages and other educational organizations) - classes and classrooms; 

Treatment and preventive, sanatorium-health and resort institutions - wards (at least 60% of the total number); 

Social service organizations (boarding homes for the disabled and elderly and other social service organizations), hospices - wards, isolation wards.	Southern zone 
(south of 48° N )	1.5 hours	from February 22 
to October 22

The absence of insolation is permitted in computer science, physics, chemistry, drawing and drafting classrooms.

- Standardized total duration of insolation in a residential area

Regulated territories	Geographical latitude of the area	Duration of insolation, not less than	Calendar period
Territories of children's playgrounds, sports grounds of residential buildings, group playgrounds of preschool organizations, sports zones, recreation areas	Northern zone (north of 58° N )	2.5 hours, 
including at least 1 hour for one of the periods in case of intermittent insolation	from April 22 
to August 22
comprehensive schools and boarding schools, recreation areas of stationary medical and educational institutions (50% of the site area, regardless of latitude)	Central zone (58° N - 48° N )	2.5 hours, 
including at least 1 hour for one of the periods in case of intermittent insolation	
	Southern zone (south of 48° N )	2.5 hours, 
including at least 1 hour for one of the periods in case of intermittent insolation	from February 22 
to October 22

To calculate the KEO, the standard indicators are prescribed in SanPiN 1.2.3685-21 tables: 5.52, 5.53, 5.54


16. What method of finishing rooms with unique architectural features, such as loggias or bay windows, do you prefer?
Residential buildings often feature loggias, balconies, and terraces. Lighting in a living space should be designed with the loggia or balcony in mind, allowing light to enter the room.

17. Which platform do you prefer for new software?

Answers:
- Web application or desktop application?
- Cloud or local installation?
- If it's a web application, should it be available offline?

18. What operating systems should the program support ( Windows , macOS , Linux )?
- Windows

19. Do you want the program to integrate with existing software or platforms such as BIM ( Revit , AutoCAD ) or ERP systems?
- Yes, Revit , AutoCAD , Renga . Ability to upload plans from AutoCAD as a background.

20. Do you have a preference for a programming language or technology stack used in software development?
- There is not

22. How would you rate the current user interfaces of existing programs ( Base , Solaris , Altec Insolations )?
- Base is an outdated program; it functions like a calculator. It's not suitable for large-scale verification.
Solaris is a complex program. It requires some understanding to use. It requires manual data entry.
- Altec Insolations is currently the best software for insolation and KEO calculations. The program is based on a BIM model, significantly simplifying the data entry process for lighting calculations. This also allows for seamless generation of graphical layouts for each floor.
When exporting, you can immediately complete both the explanatory note with stamps and signatures, and the graphic section with calculation points to enable the inspection.

23. What improvements would you like to see in the new software?
- It is important to create your own program
- the possibility of supplementing with various calculation modules in the future.
- configure the ability to calculate insolation through rooms (loggias, balconies)
- optimize the calculation error

24. Should the software be developed for specific user roles (e.g. architects, engineers, etc.)?
- Not required. By default, calculations are performed by Architects.

25. What level of user experience do you expect?
-Ideally, I would like an intuitive interface so that calculation time could be minimized.
In general, the person performing the calculation should be familiar with the requirements and mechanics of insolation and KEO calculations. However, I wouldn't want to waste time reproducing it and displaying the data.

26. Do you prefer a program to be intuitive and require minimal training, or are detailed instructions acceptable?
- ideally intuitive, but instructions are acceptable

27. Are there any special features or tools to enhance usability, such as step-by-step instructions, visual aids, or templates?
- step-by-step instructions, visual aids. Templates will likely not be required, as each project is unique. The only requirements that remain unchanged are those that should already be in the calculations.

28. What data formats are required to import and export from the program (e.g. BIM models, DWG files , spreadsheets)?
- BIM models, DWG files

29. Do you need real-time synchronization or integration with existing tools such as Revit or AutoCAD ?
- Need the ability to communicate between Revit models and Renga . DWG files are most likely to be used as a backing.

30. How do you prefer to store project data? Should it be stored in a database, in the cloud, or locally on users' computers?
- it doesn't matter

31. Do you want to retain the ability to edit and export existing models created in other programs, such as REVIT ?
- Yes. I often need to change layouts, and I'd like the ability to edit them without having to reconfigure the workspace.

32. Is version control important for project data (e.g. tracking changes over time)?
- It would be sufficient if, if recalculation is necessary, the model could be edited and the calculation run. Constant monitoring is not necessary.

33. How large or complex are the projects you typically work on? Does the software need to handle large data sets or complex buildings?
Sometimes files become very large, especially when loading districts and neighborhoods. The program needs to process the data required for the calculation and optimize the rest.

34. Are there any specific performance metrics that concern you, such as calculation speed or data processing time?
- Calculation speed and data processing time should be optimized. In Altec Insolations acceptable calculation time

35. Should the program support multiple users or be used in a collaborative environment?
- No, it's not necessary.

36. Do you require any customization for specific building types or regions?
- calculation is required according to the standards: SanPiN 1.2.3685-21, GOST R 57795-2017, SP 52.13330.2016, SP 367.1325800.2017
 
37. Do you need the ability to extend the software with additional modules in the future (e.g. for lighting design or energy modeling)?
- In the future, I'd like to be able to calculate room noise, calculate the energy efficiency of a building, and calculate evacuation times from rooms. But that's for the future. For now, I won't focus on that.

38. How often do you expect updates or upgrades to be required? Do you need a solution that can be easily updated or expanded over time?
- It is expected that updates will be required no more than once every six months to a year.

39. Are there any special software security requirements, such as encryption or secure user authentication?
- There is not

40. How should data privacy and compliance be ensured, particularly when storing sensitive project or client data?
- by creating an account with a login and password, if the program is installed only on a computer, then this is not required.

41. Should the software support cloud storage or should all data be stored locally on the user's computer?
- Not necessarily. Both options are acceptable. It probably depends on what's easier to do.

42. What is the budget allocated for this project?
-

43. What is the desired completion time for the project, including major milestones?
-

44. Are there any key deadlines we need to meet?
-

45. Will you need access to the full source code after the project is completed?
- yes

46. ​​Do you have any special preferences or restrictions regarding third-party software or libraries that should be used?
- No

47. What are your expectations regarding further service and support after the software is delivered?
-

48. How do you prefer to test software? Should a formal quality control process be implemented?
-

49. Are there any special testing requirements, such as test cases for specific building types or standards?
- there are no requirements