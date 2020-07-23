## 1.0.9 - July 23, 2020

Bug fixes:
* Previously, the permissions for the log groups were added one by one
 and in case if amount of group was large enough it would cause permission size limitation error.
 Now the permission to invoke Streamer lambda is added for all log groups. 
 
Misc:
* Added documentation for the manual test deployment.

## 1.0.8 - July 02, 2020

* Update documentation with new config option, plus release and development notes

## 1.0.7 - March 24, 2020

* Simple formatting changing the order of execution for sampling and timestamp
* Add tests